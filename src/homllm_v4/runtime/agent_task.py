import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from homllm_v4.adapters.v3_provider_factory import build_v3_provider_edit_adapter_from_params
from homllm_v4.adapters.v3_provider_patch_factory import build_v3_provider_proposed_patch_planner
from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.command import CommandPolicy
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.planning.provider_patch_planner import ProviderProposedPatchPlanRequest
from homllm_v4.runtime.agent_index import (
    AgentIndexPrepRequest,
    build_v3_agent_task_index,
    prepare_agent_task_index,
)
from homllm_v4.runtime.provider_write_verify_runner import (
    ProviderWriteVerifyRunner,
    ProviderWriteVerifyRunRequest,
)
from homllm_v4.runtime.write_verify_loop import WriteVerifyLoop
from homllm_v4.services.command_service import LocalCommandService
from homllm_v4.services.patch_service import WorkspacePatchService


@dataclass(frozen=True)
class AgentTaskRequest:
    config_path: Path
    workspace_root: Path
    artifact_root: Path
    query: str
    intent: str
    expected_behavior: str
    target_file: str | None
    verification_argv: tuple[str, ...]
    run_id: str | None = None
    live_provider_name: str = "gemini"
    live_model: str = "gemini-3.5-flash-lite"
    live_api_key: str | None = None
    live_max_output_tokens: int = 8192
    max_prompt_chars: int | None = 22000
    provider_repair_attempts: int = 1
    smoke_safe: bool = True
    prepare_index: bool = False
    index_artifact_dir: Path | None = None
    index_incremental: bool = False
    index_skip_vectors: bool = False
    index_builder: Any = build_v3_agent_task_index
    provider_builder: Any = build_v3_provider_edit_adapter_from_params
    planner_builder: Any = build_v3_provider_proposed_patch_planner
    require_live_api_key: bool = True
    verification_timeout_seconds: int | None = None
    proposal_mode: str = "full_content"


@dataclass(frozen=True)
class AgentTaskResult:
    run_id: str
    stop_reason: str
    error_code: str | None
    artifact_root: str
    patch_attempt_count: int
    provider_repair_attempt_count: int
    verification_count: int
    planner_metrics: dict[str, object]
    index_built: bool = False
    index_config_path: str | None = None
    index_artifact_paths: dict[str, str] | None = None
    index_metrics: dict[str, object] | None = None
    rollback_occurred: bool = False
    rollback_restored_count: int = 0
    rollback_deleted_count: int = 0


def run_agent_task(request: AgentTaskRequest) -> AgentTaskResult:
    if request.require_live_api_key and not request.live_api_key:
        raise ValueError("live_provider_api_key_required")
    if not request.verification_argv:
        raise ValueError("verification_argv_required")

    run_id = request.run_id or str(uuid4())
    workspace_root = Path(request.workspace_root).resolve()
    artifact_root = Path(request.artifact_root).resolve()
    artifact_manager = ArtifactManager(
        workspace_root=workspace_root,
        artifact_root=artifact_root,
    )
    artifact_manager.create_run(
        run_id,
        {
            "entrypoint": "homllm_v4.runtime.agent_task.run_agent_task",
            "query": request.query,
            "target_file": request.target_file,
            "prepare_index": request.prepare_index,
        },
    )
    config_path = Path(request.config_path)
    index_prep_result = None
    if request.prepare_index:
        index_prep_result = prepare_agent_task_index(
            AgentIndexPrepRequest(
                template_config_path=config_path,
                workspace_root=workspace_root,
                artifact_root=artifact_root,
                run_id=run_id,
                index_artifact_dir=request.index_artifact_dir,
                incremental=request.index_incremental,
                skip_vectors=request.index_skip_vectors,
                index_builder=request.index_builder,
            )
        )
        config_path = index_prep_result.config_path
    write_verify_loop = WriteVerifyLoop(
        patch_service=WorkspacePatchService(),
        command_service=LocalCommandService(
            policy=CommandPolicy(
                allowed_executables=(Path(sys.executable).name,),
                default_timeout_seconds=30,
                max_timeout_seconds=60,
            )
        ),
        artifact_manager=artifact_manager,
        event_writer=EventWriter(artifact_root / run_id / "events.jsonl"),
    )
    provider = request.provider_builder(
        provider_name=request.live_provider_name,
        model=request.live_model,
        api_key=request.live_api_key,
        temperature=0.0,
        max_output_tokens=request.live_max_output_tokens,
    )
    planner = request.planner_builder(
        config_path=config_path,
        workspace_root=workspace_root,
        edit_provider=provider,
        smoke_safe=request.smoke_safe,
        artifact_manager=artifact_manager,
        max_prompt_chars=request.max_prompt_chars,
    )
    result = ProviderWriteVerifyRunner(
        planner=planner,
        write_verify_loop=write_verify_loop,
    ).run(
        ProviderWriteVerifyRunRequest(
            task_id=run_id,
            run_id=run_id,
            workspace_root=str(workspace_root),
            plan_request=ProviderProposedPatchPlanRequest(
                task_id=run_id,
                workspace_root=str(workspace_root),
                query=request.query,
                task_class="mvp_agent_task",
                index_id=f"{run_id}:index",
                target_file=request.target_file,
                intent=request.intent,
                expected_behavior=request.expected_behavior,
                verification_argv=request.verification_argv,
                retrieval_policy={"intent": "PATCH", "top_k": 20},
                verification_timeout_seconds=request.verification_timeout_seconds,
                proposal_mode=request.proposal_mode,
            ),
            max_verification_commands=1,
            provider_repair_attempts=request.provider_repair_attempts,
            rollback_on_failure=True,
        )
    )
    rollback = _rollback_summary(result.write_results)
    return AgentTaskResult(
        run_id=run_id,
        stop_reason=result.stop_reason,
        error_code=result.error_code,
        artifact_root=str(artifact_root),
        patch_attempt_count=result.patch_attempt_count,
        provider_repair_attempt_count=result.provider_repair_attempt_count,
        verification_count=len(result.verification_results),
        planner_metrics=result.planner_metrics,
        index_built=bool(index_prep_result and index_prep_result.built),
        index_config_path=str(index_prep_result.config_path) if index_prep_result else None,
        index_artifact_paths=index_prep_result.artifact_paths if index_prep_result else None,
        index_metrics=index_prep_result.metrics if index_prep_result else None,
        rollback_occurred=rollback.occurred,
        rollback_restored_count=rollback.restored_count,
        rollback_deleted_count=rollback.deleted_count,
    )


@dataclass(frozen=True)
class _RollbackSummary:
    occurred: bool = False
    restored_count: int = 0
    deleted_count: int = 0


def _rollback_summary(write_results: tuple[object, ...]) -> _RollbackSummary:
    occurred = False
    restored_count = 0
    deleted_count = 0
    for write_result in write_results:
        rollback_result = getattr(write_result, "rollback_result", None)
        if rollback_result is None:
            continue
        if not getattr(rollback_result, "rolled_back", False):
            continue
        occurred = True
        restored_count += len(tuple(getattr(rollback_result, "restored_files", ())))
        deleted_count += len(tuple(getattr(rollback_result, "deleted_files", ())))
    return _RollbackSummary(
        occurred=occurred,
        restored_count=restored_count,
        deleted_count=deleted_count,
    )
