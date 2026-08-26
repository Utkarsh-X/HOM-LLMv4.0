from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.command import CommandRunResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.patch import PatchApplyResult, PatchRollbackRequest, PatchRollbackResult
from homllm_v4.contracts.write_loop import (
    WriteVerifyLoopRequest,
    WriteVerifyLoopResult,
    WriteVerifyStopReason,
)
from homllm_v4.ledger.events import (
    PATCH_ATTEMPTED,
    PATCH_COMPLETED,
    PATCH_ROLLED_BACK,
    REPAIR_ATTEMPTED,
    RUN_COMPLETED,
    SERVICE_FAILED,
    VERIFICATION_COMPLETED,
    RunEvent,
)
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.services.command_service import LocalCommandService
from homllm_v4.services.patch_service import WorkspacePatchService


class WriteVerifyLoop:
    def __init__(
        self,
        *,
        patch_service: WorkspacePatchService,
        command_service: LocalCommandService,
        artifact_manager: ArtifactManager,
        event_writer: EventWriter,
    ) -> None:
        self.patch_service = patch_service
        self.command_service = command_service
        self.artifact_manager = artifact_manager
        self.event_writer = event_writer

    def run(self, request: WriteVerifyLoopRequest) -> WriteVerifyLoopResult:
        if len(request.verification_commands) > request.max_verification_commands:
            return self._result(
                request,
                "budget_exhausted",
                None,
                (),
                None,
                patch_attempt_count=0,
            )

        patch_attempts = (request.patch_request,) + request.repair_patch_requests
        allowed_attempts = max(1, int(request.max_patch_attempts))
        patch_result = None
        verification_results: tuple[CommandRunResult, ...] = ()
        last_verification_stop: WriteVerifyStopReason | None = None

        for attempt_index, patch_request in enumerate(
            patch_attempts[:allowed_attempts],
            start=1,
        ):
            self._append(
                request,
                "patch",
                PATCH_ATTEMPTED if attempt_index == 1 else REPAIR_ATTEMPTED,
                {
                    "attempt_index": attempt_index,
                    "file_count": len(patch_request.patches),
                },
            )
            patch_capability = self.patch_service.apply(patch_request)
            if not patch_capability.ok:
                rollback_result = self._rollback_if_enabled(request, patch_result)
                self._append(
                    request,
                    "patch",
                    SERVICE_FAILED,
                    {"service": "patch.apply", "attempt_index": attempt_index},
                )
                return self._result(
                    request,
                    "patch_failed",
                    patch_result,
                    verification_results,
                    patch_capability.error,
                    patch_attempt_count=attempt_index,
                    rollback_result=rollback_result,
                )

            patch_result = patch_capability.output
            self._append(
                request,
                "patch",
                PATCH_COMPLETED,
                {
                    "attempt_index": attempt_index,
                    "applied": patch_result.applied,
                    "file_count": len(patch_result.file_results),
                },
            )

            allowed_side_effect_files = _patch_files(patch_result)
            snapshot_root = Path(request.workspace_root)
            before_verification, before_stats = _workspace_snapshot(
                snapshot_root,
                ignored_files=allowed_side_effect_files,
            )
            verification_results, verification_error, stop_reason = self._run_verification(request)
            side_effect_files = _changed_files_since(
                snapshot_root,
                before_contents=before_verification,
                before_stats=before_stats,
                ignored_files=allowed_side_effect_files,
            )
            if side_effect_files:
                cleaned_files = _cleanup_side_effects(
                    Path(request.workspace_root),
                    before=before_verification,
                    changed_files=side_effect_files,
                    enabled=request.rollback_on_failure,
                )
                rollback_result = self._rollback_if_enabled(request, patch_result)
                return self._result(
                    request,
                    "verification_side_effect",
                    patch_result,
                    verification_results,
                    CapabilityError(
                        code="verification_side_effect",
                        message="verification command changed files outside the patch set",
                        recoverable=True,
                        retryable=False,
                        details={
                            "changed_files": side_effect_files,
                            "cleaned_files": cleaned_files,
                        },
                    ),
                    patch_attempt_count=attempt_index,
                    rollback_result=rollback_result,
                )
            if stop_reason is None:
                return self._result(
                    request,
                    "verified",
                    patch_result,
                    verification_results,
                    None,
                    patch_attempt_count=attempt_index,
                    rollback_result=None,
                )

            if verification_error is not None:
                rollback_result = self._rollback_if_enabled(request, patch_result)
                return self._result(
                    request,
                    "verification_failed",
                    patch_result,
                    verification_results,
                    verification_error,
                    patch_attempt_count=attempt_index,
                    rollback_result=rollback_result,
                )

            last_verification_stop = stop_reason
            has_repair_budget = attempt_index < allowed_attempts
            has_repair_patch = attempt_index < len(patch_attempts)
            if not (has_repair_budget and has_repair_patch):
                exhausted_reason = (
                    "repair_budget_exhausted"
                    if allowed_attempts > 1
                    else last_verification_stop
                )
                rollback_result = self._rollback_if_enabled(request, patch_result)
                return self._result(
                    request,
                    exhausted_reason,
                    patch_result,
                    verification_results,
                    None,
                    patch_attempt_count=attempt_index,
                    rollback_result=rollback_result,
                )

        rollback_result = self._rollback_if_enabled(request, patch_result)
        return self._result(
            request,
            "repair_budget_exhausted",
            patch_result,
            verification_results,
            None,
            patch_attempt_count=min(len(patch_attempts), allowed_attempts),
            rollback_result=rollback_result,
        )

    def _run_verification(
        self,
        request: WriteVerifyLoopRequest,
    ) -> tuple[tuple[CommandRunResult, ...], CapabilityError | None, WriteVerifyStopReason | None]:
        verification_results: list[CommandRunResult] = []
        for index, command in enumerate(request.verification_commands, start=1):
            command_result = self.command_service.run(command)
            if not command_result.ok:
                self._append(
                    request,
                    "verification",
                    SERVICE_FAILED,
                    {"service": "command.run", "index": index},
                )
                return tuple(verification_results), command_result.error, "verification_failed"

            verification_results.append(command_result.output)
            self._append(
                request,
                "verification",
                VERIFICATION_COMPLETED,
                {
                    "index": index,
                    "exit_code": command_result.output.exit_code,
                    "timed_out": command_result.output.timed_out,
                },
            )
            if command_result.output.timed_out:
                return tuple(verification_results), None, "verification_timeout"
            if command_result.output.exit_code != 0:
                return tuple(verification_results), None, "verification_failed"
        return tuple(verification_results), None, None

    def _result(
        self,
        request: WriteVerifyLoopRequest,
        stop_reason: WriteVerifyStopReason,
        patch_result: PatchApplyResult | None,
        verification_results: tuple[CommandRunResult, ...],
        error: CapabilityError | None,
        *,
        patch_attempt_count: int,
        rollback_result: PatchRollbackResult | None = None,
    ) -> WriteVerifyLoopResult:
        result = WriteVerifyLoopResult(
            task_id=request.task_id,
            run_id=request.run_id,
            stop_reason=stop_reason,
            patch_result=patch_result,
            verification_results=verification_results,
            response_text=self._response_text(stop_reason, verification_results),
            patch_attempt_count=patch_attempt_count,
            error=error,
            rollback_result=rollback_result,
        )
        self._append(
            request,
            "stopped",
            RUN_COMPLETED,
            {
                "stop_reason": stop_reason,
                "verification_count": len(verification_results),
                "patch_attempt_count": patch_attempt_count,
                "rolled_back": rollback_result.rolled_back if rollback_result else False,
            },
        )
        self.artifact_manager.write_json(
            "response/write_verify_loop_result.json",
            result,
            "response",
            "write-verify loop result",
        )
        return result

    @staticmethod
    def _response_text(
        stop_reason: WriteVerifyStopReason,
        verification_results: tuple[CommandRunResult, ...],
    ) -> str:
        if stop_reason == "verified":
            return f"Patch verified by {len(verification_results)} command(s)."
        return f"Write-verify loop stopped with reason: {stop_reason}."

    def _rollback_if_enabled(
        self,
        request: WriteVerifyLoopRequest,
        patch_result: PatchApplyResult | None,
    ) -> PatchRollbackResult | None:
        if not request.rollback_on_failure:
            return None
        if patch_result is None or not patch_result.applied:
            return None
        rollback = self.patch_service.rollback(
            PatchRollbackRequest(
                task_id=request.task_id,
                workspace_root=request.workspace_root,
                file_results=patch_result.file_results,
            )
        )
        if rollback.ok and rollback.output is not None:
            self._append(
                request,
                "rollback",
                PATCH_ROLLED_BACK,
                {
                    "restored_count": len(rollback.output.restored_files),
                    "deleted_count": len(rollback.output.deleted_files),
                },
            )
            return rollback.output
        self._append(
            request,
            "rollback",
            SERVICE_FAILED,
            {"service": "patch.rollback", "code": rollback.error.code if rollback.error else None},
        )
        return None

    def _append(
        self,
        request: WriteVerifyLoopRequest,
        phase: str,
        event_type: str,
        summary: dict[str, object],
    ) -> None:
        self.event_writer.append(
            RunEvent(
                event_id=str(uuid4()),
                run_id=request.run_id,
                task_id=request.task_id,
                phase=phase,
                event_type=event_type,
                timestamp="",
                summary=summary,
                artifact_refs=(),
            )
        )


def _patch_files(patch_result: PatchApplyResult | None) -> tuple[str, ...]:
    if patch_result is None:
        return ()
    return tuple(file_result.file_path for file_result in patch_result.file_results)


@dataclass(frozen=True)
class _FileStat:
    size: int
    mtime_ns: int


def _workspace_snapshot(
    root: Path, *, ignored_files: tuple[str, ...]
) -> tuple[dict[str, bytes], dict[str, _FileStat]]:
    ignored = {Path(file_path).as_posix() for file_path in ignored_files}
    contents: dict[str, bytes] = {}
    stats: dict[str, _FileStat] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in ignored or _ignored_snapshot_path(relative):
            continue
        stat = path.stat()
        contents[relative] = path.read_bytes()
        stats[relative] = _FileStat(stat.st_size, stat.st_mtime_ns)
    return contents, stats


def _workspace_index(root: Path, *, ignored_files: tuple[str, ...]) -> dict[str, _FileStat]:
    ignored = {Path(file_path).as_posix() for file_path in ignored_files}
    stats: dict[str, _FileStat] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in ignored or _ignored_snapshot_path(relative):
            continue
        stat = path.stat()
        stats[relative] = _FileStat(stat.st_size, stat.st_mtime_ns)
    return stats


def _changed_files_since(
    root: Path,
    *,
    before_contents: dict[str, bytes],
    before_stats: dict[str, _FileStat],
    ignored_files: tuple[str, ...],
) -> tuple[str, ...]:
    """Detect workspace changes without re-reading unchanged files.

    The after-side walk collects only ``(size, mtime_ns)`` metadata; file
    bytes are re-read exclusively for entries that are new, missing, or whose
    metadata differs from the pre-verification snapshot. Entries with
    identical metadata are assumed unchanged (filesystem mtime granularity
    makes a silent same-size, same-mtime_ns rewrite vanishingly unlikely,
    and the pre-verification byte snapshot remains fully eager so rollback
    restoration is always possible).
    """
    after_stats = _workspace_index(root, ignored_files=ignored_files)
    candidates = {
        relative
        for relative, stat in after_stats.items()
        if relative not in before_stats or before_stats[relative] != stat
    }
    candidates.update(relative for relative in before_stats if relative not in after_stats)
    changed: list[str] = []
    for relative in sorted(candidates):
        if relative not in after_stats:
            changed.append(relative)
            continue
        if before_contents.get(relative) != (root / relative).read_bytes():
            changed.append(relative)
    return tuple(changed)


def _cleanup_side_effects(
    root: Path,
    *,
    before: dict[str, bytes],
    changed_files: tuple[str, ...],
    enabled: bool,
) -> tuple[str, ...]:
    if not enabled:
        return ()

    cleaned: list[str] = []
    resolved_root = root.resolve()
    for relative in changed_files:
        path = (resolved_root / relative).resolve()
        try:
            path.relative_to(resolved_root)
        except ValueError:
            continue

        if relative in before:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(before[relative])
            cleaned.append(relative)
        elif path.exists() and path.is_file():
            path.unlink()
            cleaned.append(relative)
    return tuple(cleaned)


_SNAPSHOT_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".homllm",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".ruff_cache",
        ".idea",
        ".vscode",
    }
)


def _ignored_snapshot_path(relative_path: str) -> bool:
    parts = set(Path(relative_path).parts)
    if parts & _SNAPSHOT_IGNORED_DIRS:
        return True
    return relative_path.endswith((".pyc", ".pyo"))
