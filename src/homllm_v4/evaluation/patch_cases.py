from pathlib import Path

from homllm_v4.contracts.command import CommandRunRequest
from homllm_v4.contracts.evaluation import EvaluationCase
from homllm_v4.contracts.patch import FilePatch, PatchApplyRequest
from homllm_v4.contracts.write_loop import WriteVerifyLoopRequest


def build_write_verify_request_from_case(
    case: EvaluationCase,
    *,
    workspace_root: Path,
    run_id: str,
) -> WriteVerifyLoopRequest:
    payload = case.input_payload
    file_path = _required_str(payload, "file_path")
    expected_hash = _optional_str(payload, "expected_content_hash")
    new_content = _required_str(payload, "new_content")
    verification_argv = _required_str_tuple(payload, "verification_argv")
    allowed_file_paths = _optional_str_tuple(payload, "allowed_file_paths")
    max_patch_attempts = _optional_int(payload, "max_patch_attempts", default=1)

    patch_request = PatchApplyRequest(
        task_id=case.case_id,
        workspace_root=str(workspace_root),
        patches=(FilePatch(file_path, expected_hash, new_content),),
        allowed_file_paths=allowed_file_paths,
        max_file_changes=1,
    )
    verification = CommandRunRequest(
        task_id=case.case_id,
        workspace_root=str(workspace_root),
        cwd=".",
        argv=verification_argv,
        timeout_seconds=10,
    )
    return WriteVerifyLoopRequest(
        task_id=case.case_id,
        run_id=run_id,
        workspace_root=str(workspace_root),
        patch_request=patch_request,
        verification_commands=(verification,),
        max_verification_commands=1,
        max_patch_attempts=max_patch_attempts,
    )


def _required_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"missing string payload field: {key}")
    return value


def _optional_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"invalid string payload field: {key}")
    return value


def _required_str_tuple(payload: dict[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"missing string sequence payload field: {key}")
    return tuple(value)


def _optional_str_tuple(payload: dict[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"invalid string sequence payload field: {key}")
    return tuple(value)


def _optional_int(payload: dict[str, object], key: str, *, default: int) -> int:
    value = payload.get(key, default)
    if not isinstance(value, int):
        raise ValueError(f"invalid integer payload field: {key}")
    return value
