import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from homllm_v4.runtime.agent_session import AgentSessionRequest, AgentSessionResult
from homllm_v4.runtime.agent_session import run_agent_session
from homllm_v4.serialization.json import to_jsonable


@dataclass(frozen=True)
class HomllmAgentRunRequest:
    config_path: Path
    workspace_root: Path
    artifact_root: Path
    query: str
    run_id: str | None = None
    max_passes: int = 1
    smoke_safe: bool = True
    answer_provider_mode: str = "summary"
    edit_intent: str | None = None
    expected_behavior: str | None = None
    target_file: str | None = None
    verification_argv: tuple[str, ...] = ()
    live_provider_name: str = "gemini"
    live_model: str = "gemini-3.5-flash-lite"
    live_api_key: str | None = None
    live_max_output_tokens: int = 8192
    max_prompt_chars: int | None = 22000
    provider_repair_attempts: int = 1
    prepare_index: bool = False
    index_artifact_dir: Path | None = None
    index_incremental: bool = False
    index_skip_vectors: bool = False
    session_runner: Any = run_agent_session
    edit_provider_builder: Any = None
    edit_require_live_api_key: bool = True


@dataclass(frozen=True)
class HomllmAgentRunResult:
    run_id: str
    stop_reason: str
    error_code: str | None
    session_state_path: str
    trajectory_path: str
    artifact_root: str
    answer_text: str
    answer_provider_mode: str
    ask_stop_reason: str
    edit_stop_reason: str | None
    patch_attempt_count: int
    provider_repair_attempt_count: int
    verification_count: int
    index_built: bool
    index_config_path: str | None
    index_artifact_paths: dict[str, str] | None
    index_metrics: dict[str, object] | None
    rollback_occurred: bool = False
    rollback_restored_count: int = 0
    rollback_deleted_count: int = 0


def run_homllm_agent(request: HomllmAgentRunRequest) -> HomllmAgentRunResult:
    run_id = request.run_id or str(uuid4())
    session_result = request.session_runner(
        AgentSessionRequest(
            config_path=request.config_path,
            workspace_root=request.workspace_root,
            artifact_root=request.artifact_root,
            run_id=run_id,
            query=request.query,
            max_passes=request.max_passes,
            smoke_safe=request.smoke_safe,
            answer_provider_mode=request.answer_provider_mode,
            persist_session_state=True,
            edit_intent=request.edit_intent,
            expected_behavior=request.expected_behavior,
            target_file=request.target_file,
            verification_argv=request.verification_argv,
            live_provider_name=request.live_provider_name,
            live_model=request.live_model,
            live_api_key=request.live_api_key,
            live_max_output_tokens=request.live_max_output_tokens,
            max_prompt_chars=request.max_prompt_chars,
            provider_repair_attempts=request.provider_repair_attempts,
            prepare_index=request.prepare_index,
            index_artifact_dir=request.index_artifact_dir,
            index_incremental=request.index_incremental,
            index_skip_vectors=request.index_skip_vectors,
            edit_provider_builder=request.edit_provider_builder,
            edit_require_live_api_key=request.edit_require_live_api_key,
        )
    )
    artifact_root = Path(session_result.artifact_root)
    run_dir = (artifact_root / session_result.run_id).resolve()
    _ensure_inside(run_dir, artifact_root.resolve())
    run_dir.mkdir(parents=True, exist_ok=True)
    session_state_path = run_dir / "session.json"
    trajectory_path = run_dir / "trajectory.json"
    result = HomllmAgentRunResult(
        run_id=session_result.run_id,
        stop_reason=_overall_stop_reason(session_result),
        error_code=(
            session_result.edit_error_code
            if request.edit_intent is not None
            else session_result.answer_error_code
        ),
        session_state_path=str(session_state_path),
        trajectory_path=str(trajectory_path),
        artifact_root=session_result.artifact_root,
        answer_text=session_result.answer_text,
        answer_provider_mode=session_result.answer_provider_mode,
        ask_stop_reason=session_result.ask_stop_reason,
        edit_stop_reason=session_result.edit_stop_reason,
        patch_attempt_count=session_result.patch_attempt_count,
        provider_repair_attempt_count=session_result.provider_repair_attempt_count,
        verification_count=session_result.verification_count,
        index_built=session_result.index_built,
        index_config_path=session_result.index_config_path,
        index_artifact_paths=session_result.index_artifact_paths,
        index_metrics=session_result.index_metrics,
        rollback_occurred=session_result.rollback_occurred,
        rollback_restored_count=session_result.rollback_restored_count,
        rollback_deleted_count=session_result.rollback_deleted_count,
    )
    _write_trajectory(trajectory_path, request, session_result, result)
    return result


def _overall_stop_reason(result: AgentSessionResult) -> str:
    return result.edit_stop_reason or result.ask_stop_reason


def _write_trajectory(
    path: Path,
    request: HomllmAgentRunRequest,
    session_result: AgentSessionResult,
    result: HomllmAgentRunResult,
) -> None:
    payload = {
        "schema_version": 1,
        "entrypoint": "homllm-agent run",
        "run_id": result.run_id,
        "query": request.query,
        "artifact_root": result.artifact_root,
        "session_state_path": result.session_state_path,
        "trajectory_path": result.trajectory_path,
        "stop_reason": result.stop_reason,
        "error_code": result.error_code,
        "answer_text": result.answer_text,
        "steps": [
            {
                "name": "repo_index",
                "status": "built" if session_result.index_built else "loaded",
                "config_path": session_result.index_config_path,
            },
            {
                "name": "grounded_answer",
                "status": session_result.ask_stop_reason,
                "provider_mode": session_result.answer_provider_mode,
            },
            {
                "name": "bounded_edit",
                "status": session_result.edit_stop_reason or "skipped",
                "patch_attempt_count": session_result.patch_attempt_count,
            },
            {
                "name": "verification",
                "status": _verification_status(session_result),
                "verification_count": session_result.verification_count,
            },
            {
                "name": "rollback",
                "status": _rollback_status(session_result),
                "occurred": session_result.rollback_occurred,
                "restored_count": session_result.rollback_restored_count,
                "deleted_count": session_result.rollback_deleted_count,
            },
        ],
        "metrics": {
            "answer": session_result.answer_metrics,
            "planner": session_result.planner_metrics,
            "index": session_result.index_metrics,
            "provider_repair_attempt_count": (
                session_result.provider_repair_attempt_count
            ),
            "rollback_occurred": session_result.rollback_occurred,
            "rollback_restored_count": session_result.rollback_restored_count,
            "rollback_deleted_count": session_result.rollback_deleted_count,
        },
    }
    temp_path = path.with_name(".trajectory.json.tmp")
    temp_path.write_text(
        json.dumps(to_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="",
    )
    temp_path.replace(path)


def _verification_status(result: AgentSessionResult) -> str:
    if result.edit_stop_reason is None:
        return "skipped"
    if result.edit_stop_reason == "verified" and result.edit_error_code is None:
        return "passed"
    return "failed"


def _rollback_status(result: AgentSessionResult) -> str:
    if result.edit_stop_reason is None:
        return "skipped"
    if not result.rollback_occurred:
        return "not_required"
    return "performed"


def _ensure_inside(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"agent_run_path_denied: {path}") from exc
