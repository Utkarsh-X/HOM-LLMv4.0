from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from homllm_v4.adapters.v3_provider_factory import build_v3_provider_edit_adapter_from_params
from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.runtime.agent_task import AgentTaskRequest
from homllm_v4.runtime.agent_task import run_agent_task
from homllm_v4.runtime.agent_index import (
    AgentIndexPrepRequest,
    build_v3_agent_task_index,
    prepare_agent_task_index,
)
from homllm_v4.runtime.grounded_answer import (
    GroundedAnswerRequest,
    GroundedAnswerSynthesizer,
)
from homllm_v4.runtime.session_state import AgentSessionStore, AgentSessionTurn


@dataclass(frozen=True)
class AgentSessionRequest:
    config_path: Path
    workspace_root: Path
    artifact_root: Path
    query: str
    run_id: str | None = None
    max_passes: int = 1
    smoke_safe: bool = True
    answer_provider_mode: str = "summary"
    answer_synthesizer: Any = None
    answer_provider_builder: Any = build_v3_provider_edit_adapter_from_params
    edit_provider_builder: Any = None
    edit_require_live_api_key: bool = True
    persist_session_state: bool = True
    edit_intent: str | None = None
    expected_behavior: str | None = None
    target_file: str | None = None
    verification_argv: tuple[str, ...] = ()
    live_provider_name: str = "gemini"
    live_model: str = "gemini-3.1-flash-lite-preview"
    live_api_key: str | None = None
    live_max_output_tokens: int = 8192
    max_prompt_chars: int | None = 22000
    provider_repair_attempts: int = 1
    prepare_index: bool = False
    index_artifact_dir: Path | None = None
    index_incremental: bool = False
    index_skip_vectors: bool = False
    index_builder: Any = build_v3_agent_task_index
    read_only_runner: Any = None
    edit_runner: Any = run_agent_task


@dataclass(frozen=True)
class AgentSessionResult:
    run_id: str
    ask_run_id: str
    ask_stop_reason: str
    answer_text: str
    answer_provider_mode: str
    answer_error_code: str | None
    answer_metrics: dict[str, object]
    edit_run_id: str | None
    edit_stop_reason: str | None
    edit_error_code: str | None
    artifact_root: str
    patch_attempt_count: int
    provider_repair_attempt_count: int
    verification_count: int
    planner_metrics: dict[str, object]
    index_built: bool
    index_config_path: str | None
    index_artifact_paths: dict[str, str] | None
    index_metrics: dict[str, object] | None
    rollback_occurred: bool = False
    rollback_restored_count: int = 0
    rollback_deleted_count: int = 0


def run_agent_session(request: AgentSessionRequest) -> AgentSessionResult:
    run_id = request.run_id or str(uuid4())
    artifact_root = Path(request.artifact_root)
    config_path = Path(request.config_path)
    index_prep_result = None
    if request.prepare_index:
        index_prep_result = prepare_agent_task_index(
            AgentIndexPrepRequest(
                template_config_path=config_path,
                workspace_root=Path(request.workspace_root),
                artifact_root=artifact_root,
                run_id=run_id,
                index_artifact_dir=request.index_artifact_dir,
                incremental=request.index_incremental,
                skip_vectors=request.index_skip_vectors,
                index_builder=request.index_builder,
            )
        )
        config_path = index_prep_result.config_path
    ask_run_id = f"{run_id}-ask"
    read_only_runner = request.read_only_runner or _default_read_only_runner()
    ask_result = read_only_runner(
        config_path=config_path,
        workspace_root=Path(request.workspace_root),
        query=request.query,
        run_id=ask_run_id,
        artifact_root=artifact_root,
        max_passes=request.max_passes,
        smoke_safe=request.smoke_safe,
    )
    answer_text = ask_result.response_text
    answer_error_code = None
    answer_metrics: dict[str, object] = {}
    if request.answer_provider_mode == "live":
        answer_result = _synthesize_grounded_answer(
            request=request,
            workspace_root=Path(request.workspace_root),
            artifact_root=artifact_root,
            ask_run_id=ask_run_id,
            ask_result=ask_result,
        )
        answer_error_code = answer_result.error_code
        answer_metrics = answer_result.metrics
        if answer_result.ok:
            answer_text = answer_result.answer_text
    elif request.answer_provider_mode != "summary":
        raise ValueError(f"unsupported_answer_provider_mode: {request.answer_provider_mode}")

    edit_result = None
    edit_run_id = None
    if request.edit_intent is not None:
        if request.expected_behavior is None:
            raise ValueError("expected_behavior_required")
        if not request.verification_argv:
            raise ValueError("verification_argv_required")
        edit_run_id = f"{run_id}-edit"
        edit_result = request.edit_runner(
            AgentTaskRequest(
                config_path=config_path,
                workspace_root=Path(request.workspace_root),
                artifact_root=artifact_root,
                run_id=edit_run_id,
                query=request.query,
                intent=request.edit_intent,
                expected_behavior=request.expected_behavior,
                target_file=request.target_file,
                verification_argv=request.verification_argv,
                live_provider_name=request.live_provider_name,
                live_model=request.live_model,
                live_api_key=request.live_api_key,
                live_max_output_tokens=request.live_max_output_tokens,
                max_prompt_chars=request.max_prompt_chars,
                provider_repair_attempts=request.provider_repair_attempts,
                smoke_safe=request.smoke_safe,
                prepare_index=False,
                index_artifact_dir=request.index_artifact_dir,
                index_incremental=request.index_incremental,
                index_skip_vectors=request.index_skip_vectors,
                provider_builder=(
                    request.edit_provider_builder
                    if request.edit_provider_builder is not None
                    else build_v3_provider_edit_adapter_from_params
                ),
                require_live_api_key=request.edit_require_live_api_key,
            )
        )

    result = AgentSessionResult(
        run_id=run_id,
        ask_run_id=ask_run_id,
        ask_stop_reason=ask_result.stop_reason,
        answer_text=answer_text,
        answer_provider_mode=request.answer_provider_mode,
        answer_error_code=answer_error_code,
        answer_metrics=answer_metrics,
        edit_run_id=edit_run_id,
        edit_stop_reason=edit_result.stop_reason if edit_result else None,
        edit_error_code=edit_result.error_code if edit_result else None,
        artifact_root=str(artifact_root),
        patch_attempt_count=edit_result.patch_attempt_count if edit_result else 0,
        provider_repair_attempt_count=(
            edit_result.provider_repair_attempt_count if edit_result else 0
        ),
        verification_count=edit_result.verification_count if edit_result else 0,
        planner_metrics=edit_result.planner_metrics if edit_result else {},
        rollback_occurred=edit_result.rollback_occurred if edit_result else False,
        rollback_restored_count=(
            edit_result.rollback_restored_count if edit_result else 0
        ),
        rollback_deleted_count=edit_result.rollback_deleted_count if edit_result else 0,
        index_built=bool(
            (index_prep_result and index_prep_result.built)
            or (edit_result and edit_result.index_built)
        ),
        index_config_path=(
            str(index_prep_result.config_path)
            if index_prep_result
            else edit_result.index_config_path
            if edit_result
            else None
        ),
        index_artifact_paths=(
            index_prep_result.artifact_paths
            if index_prep_result
            else edit_result.index_artifact_paths
            if edit_result
            else None
        ),
        index_metrics=(
            index_prep_result.metrics
            if index_prep_result
            else edit_result.index_metrics
            if edit_result
            else None
        ),
    )
    if request.persist_session_state:
        _persist_session_turn(
            request=request,
            result=result,
            config_path=config_path,
            workspace_root=Path(request.workspace_root),
            artifact_root=artifact_root,
        )
    return result


def _default_read_only_runner():
    from homllm_v4.api import run_read_only_query

    return run_read_only_query


def _persist_session_turn(
    *,
    request: AgentSessionRequest,
    result: AgentSessionResult,
    config_path: Path,
    workspace_root: Path,
    artifact_root: Path,
) -> None:
    store = AgentSessionStore(artifact_root=artifact_root, session_id=result.run_id)
    state = store.create_or_load(
        workspace_root=workspace_root,
        config_path=config_path,
        instruction=request.query,
    )
    store.update_index_metadata(
        index_built=result.index_built,
        index_config_path=result.index_config_path,
        index_artifact_paths=result.index_artifact_paths,
        index_metrics=result.index_metrics,
    )
    metrics = {
        **result.answer_metrics,
        **result.planner_metrics,
        "patch_attempt_count": result.patch_attempt_count,
        "provider_repair_attempt_count": result.provider_repair_attempt_count,
        "verification_count": result.verification_count,
        "index_built": result.index_built,
        "rollback_occurred": result.rollback_occurred,
        "rollback_restored_count": result.rollback_restored_count,
        "rollback_deleted_count": result.rollback_deleted_count,
    }
    store.append_turn(
        AgentSessionTurn(
            turn_index=len(state.turns) + 1,
            query=request.query,
            ask_run_id=result.ask_run_id,
            ask_stop_reason=result.ask_stop_reason,
            answer_text=result.answer_text,
            answer_provider_mode=result.answer_provider_mode,
            answer_error_code=result.answer_error_code,
            edit_run_id=result.edit_run_id,
            edit_stop_reason=result.edit_stop_reason,
            edit_error_code=result.edit_error_code,
            metrics=metrics,
        )
    )


def _synthesize_grounded_answer(
    *,
    request: AgentSessionRequest,
    workspace_root: Path,
    artifact_root: Path,
    ask_run_id: str,
    ask_result,
):
    if request.answer_synthesizer is not None:
        synthesizer = request.answer_synthesizer
    else:
        if not request.live_api_key:
            raise ValueError("live_provider_api_key_required")
        artifact_manager = ArtifactManager(
            workspace_root=workspace_root,
            artifact_root=artifact_root,
        )
        artifact_manager.create_run(
            ask_run_id,
            {
                "entrypoint": "homllm_v4.runtime.agent_session.answer",
                "query": request.query,
            },
        )
        provider = request.answer_provider_builder(
            provider_name=request.live_provider_name,
            model=request.live_model,
            api_key=request.live_api_key,
            temperature=0.0,
            max_output_tokens=request.live_max_output_tokens,
        )
        synthesizer = GroundedAnswerSynthesizer(
            provider=provider,
            artifact_manager=artifact_manager,
            max_prompt_chars=request.max_prompt_chars,
        )
    return synthesizer.synthesize(
        GroundedAnswerRequest(
            task_id=ask_run_id,
            query=request.query,
            context_pack=ask_result.context_pack,
        )
    )
