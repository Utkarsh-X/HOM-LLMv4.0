import hashlib
from pathlib import Path
from time import perf_counter

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import DirectReadRequest, DirectReadResult
from homllm_v4.contracts.telemetry import CapabilityTelemetry


class DirectReadService:
    def __init__(self, *, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()

    def read(self, request: DirectReadRequest) -> CapabilityResult[DirectReadResult]:
        started = perf_counter()
        path = (self.workspace_root / request.file_path).resolve()

        try:
            path.relative_to(self.workspace_root)
        except ValueError:
            return self._failure(
                code="path_denied",
                message="path is outside workspace",
                request=request,
                started=started,
                details={"file_path": request.file_path},
            )

        if not path.exists() or not path.is_file():
            return self._failure(
                code="file_not_found",
                message="file does not exist",
                request=request,
                started=started,
                details={"file_path": request.file_path},
            )

        try:
            size = path.stat().st_size
        except OSError as exc:
            return self._failure(
                code="read_failed",
                message=str(exc),
                request=request,
                started=started,
                details={"file_path": request.file_path},
            )

        if size > request.max_bytes:
            return self._failure(
                code="file_too_large",
                message="file exceeds max_bytes",
                request=request,
                started=started,
                details={"size": size, "max_bytes": request.max_bytes},
            )

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return self._failure(
                code="binary_file_denied",
                message="file is not valid utf-8 text",
                request=request,
                started=started,
                details={"file_path": request.file_path},
            )
        except OSError as exc:
            return self._failure(
                code="read_failed",
                message=str(exc),
                request=request,
                started=started,
                details={"file_path": request.file_path},
            )

        excerpt = self._slice_lines(text, request.line_start, request.line_end)
        output = DirectReadResult(
            file_path=request.file_path,
            content_excerpt=excerpt,
            line_start=request.line_start,
            line_end=request.line_end,
            content_hash=self._hash_text(text) if request.require_hash else None,
            truncated=False,
            freshness="fresh",
        )
        return CapabilityResult(
            capability_name="file.read",
            ok=True,
            output=output,
            error=None,
            telemetry=self._telemetry(
                request=request,
                started=started,
                output_summary={"bytes": len(text.encode("utf-8"))},
            ),
            artifacts=(),
        )

    def _failure(
        self,
        *,
        code: str,
        message: str,
        request: DirectReadRequest,
        started: float,
        details: dict[str, object],
    ) -> CapabilityResult[DirectReadResult]:
        return CapabilityResult(
            capability_name="file.read",
            ok=False,
            output=None,
            error=CapabilityError(
                code=code,
                message=message,
                recoverable=code in {"file_not_found", "file_too_large"},
                retryable=False,
                details=details,
            ),
            telemetry=self._telemetry(request=request, started=started, output_summary={}),
            artifacts=(),
        )

    @staticmethod
    def _slice_lines(text: str, line_start: int | None, line_end: int | None) -> str:
        if line_start is None and line_end is None:
            return text
        lines = text.splitlines(keepends=True)
        start_index = max((line_start or 1) - 1, 0)
        end_index = line_end if line_end is not None else len(lines)
        return "".join(lines[start_index:end_index])

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()

    @staticmethod
    def _telemetry(
        *,
        request: DirectReadRequest,
        started: float,
        output_summary: dict[str, object],
    ) -> CapabilityTelemetry:
        return CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=int((perf_counter() - started) * 1000),
            input_summary={"file_path": request.file_path, "max_bytes": request.max_bytes},
            output_summary=output_summary,
            token_usage={},
            model_usage={},
            degraded=False,
            degradation_reason=None,
        )
