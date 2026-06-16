import difflib
import hashlib
from pathlib import Path
from time import perf_counter

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.patch import (
    FilePatch,
    FilePatchResult,
    PatchApplyRequest,
    PatchApplyResult,
    PatchRollbackRequest,
    PatchRollbackResult,
)
from homllm_v4.contracts.telemetry import CapabilityTelemetry


class WorkspacePatchService:
    def apply(self, request: PatchApplyRequest) -> CapabilityResult[PatchApplyResult]:
        started = perf_counter()
        workspace_root = Path(request.workspace_root).resolve()
        file_results: list[FilePatchResult] = []
        inspection_error = self._inspect_request(request)
        if inspection_error is not None:
            return self._failed(
                request,
                started,
                "diff_inspection_failed",
                inspection_error,
            )

        for patch in request.patches:
            target = (workspace_root / patch.file_path).resolve()
            try:
                target.relative_to(workspace_root)
            except ValueError:
                return self._failed(request, started, "path_denied", f"path escapes workspace: {target}")

            old_file_existed = target.exists()
            old_content = target.read_text(encoding="utf-8") if old_file_existed else ""
            old_hash = self._content_hash(old_content) if old_file_existed else None
            if patch.expected_content_hash is not None and old_hash != patch.expected_content_hash:
                return self._failed(
                    request,
                    started,
                    "stale_context",
                    f"content hash mismatch for {patch.file_path}",
                )

            file_results.append(
                FilePatchResult(
                    file_path=patch.file_path,
                    old_content_hash=old_hash,
                    new_content_hash=self._content_hash(patch.new_content),
                    diff=self._diff(patch, old_content),
                    old_content=old_content if old_file_existed else None,
                    old_file_existed=old_file_existed,
                )
            )

        if not request.dry_run:
            for patch in request.patches:
                target = (workspace_root / patch.file_path).resolve()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(patch.new_content, encoding="utf-8")

        output = PatchApplyResult(
            applied=not request.dry_run,
            file_results=tuple(file_results),
        )
        return CapabilityResult(
            capability_name="patch.apply",
            ok=True,
            output=output,
            error=None,
            telemetry=self._telemetry(
                request,
                started,
                {"applied": output.applied, "file_count": len(output.file_results)},
            ),
            artifacts=(),
        )

    def rollback(self, request: PatchRollbackRequest) -> CapabilityResult[PatchRollbackResult]:
        started = perf_counter()
        workspace_root = Path(request.workspace_root).resolve()
        restored_files: list[str] = []
        deleted_files: list[str] = []

        for file_result in request.file_results:
            target = (workspace_root / file_result.file_path).resolve()
            try:
                target.relative_to(workspace_root)
            except ValueError:
                return CapabilityResult(
                    capability_name="patch.rollback",
                    ok=False,
                    output=None,
                    error=CapabilityError(
                        code="path_denied",
                        message=f"path escapes workspace: {target}",
                        recoverable=True,
                        retryable=False,
                        details={"file_path": file_result.file_path},
                    ),
                    telemetry=self._rollback_telemetry(
                        request,
                        started,
                        {"code": "path_denied"},
                    ),
                    artifacts=(),
                )

            if file_result.old_file_existed:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(file_result.old_content or "", encoding="utf-8")
                restored_files.append(file_result.file_path)
            elif target.exists():
                target.unlink()
                deleted_files.append(file_result.file_path)

        output = PatchRollbackResult(
            rolled_back=True,
            restored_files=tuple(restored_files),
            deleted_files=tuple(deleted_files),
        )
        return CapabilityResult(
            capability_name="patch.rollback",
            ok=True,
            output=output,
            error=None,
            telemetry=self._rollback_telemetry(
                request,
                started,
                {
                    "restored_count": len(restored_files),
                    "deleted_count": len(deleted_files),
                },
            ),
            artifacts=(),
        )

    def _failed(
        self,
        request: PatchApplyRequest,
        started: float,
        code: str,
        message: str,
    ) -> CapabilityResult[PatchApplyResult]:
        return CapabilityResult(
            capability_name="patch.apply",
            ok=False,
            output=None,
            error=CapabilityError(
                code=code,
                message=message,
                recoverable=True,
                retryable=False,
                details={"file_count": len(request.patches)},
            ),
            telemetry=self._telemetry(request, started, {"code": code}),
            artifacts=(),
        )

    @staticmethod
    def _inspect_request(request: PatchApplyRequest) -> str | None:
        if request.max_file_changes is not None and len(request.patches) > request.max_file_changes:
            return (
                f"patch changes {len(request.patches)} files, "
                f"limit is {request.max_file_changes}"
            )
        if request.allowed_file_paths:
            allowed = {Path(path).as_posix() for path in request.allowed_file_paths}
            for patch in request.patches:
                if Path(patch.file_path).as_posix() not in allowed:
                    return f"unexpected file change: {patch.file_path}"
        return None

    @classmethod
    def _diff(cls, patch: FilePatch, old_content: str) -> str:
        old_lines = old_content.splitlines(keepends=True)
        new_lines = patch.new_content.splitlines(keepends=True)
        return "".join(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{patch.file_path}",
                tofile=f"b/{patch.file_path}",
            )
        )

    @staticmethod
    def _content_hash(text: str) -> str:
        return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((perf_counter() - started) * 1000)

    def _telemetry(
        self,
        request: PatchApplyRequest,
        started: float,
        output_summary: dict[str, object],
    ) -> CapabilityTelemetry:
        return CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=self._duration_ms(started),
            input_summary={"task_id": request.task_id, "dry_run": request.dry_run},
            output_summary=output_summary,
            token_usage={},
            model_usage={},
            degraded=False,
            degradation_reason=None,
        )

    def _rollback_telemetry(
        self,
        request: PatchRollbackRequest,
        started: float,
        output_summary: dict[str, object],
    ) -> CapabilityTelemetry:
        return CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=self._duration_ms(started),
            input_summary={"task_id": request.task_id, "file_count": len(request.file_results)},
            output_summary=output_summary,
            token_usage={},
            model_usage={},
            degraded=False,
            degradation_reason=None,
        )
