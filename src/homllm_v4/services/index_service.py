from pathlib import Path
from time import perf_counter

from homllm_v4.adapters.v3_index_adapter import V3IndexAdapter
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.index import IndexRequest, IndexValidation
from homllm_v4.contracts.telemetry import CapabilityTelemetry


class IndexService:
    def __init__(self, adapter: V3IndexAdapter | None = None) -> None:
        self.adapter = adapter or V3IndexAdapter()

    def validate(self, request: IndexRequest) -> CapabilityResult[IndexValidation]:
        started = perf_counter()
        missing = [
            path
            for path in request.artifact_paths.values()
            if not Path(path).exists()
        ]
        if missing or not request.artifact_paths:
            return CapabilityResult(
                capability_name="index.validate",
                ok=False,
                output=None,
                error=CapabilityError(
                    code="index_missing",
                    message="one or more index artifacts are missing",
                    recoverable=True,
                    retryable=False,
                    details={"missing": missing, "artifact_paths": request.artifact_paths},
                ),
                telemetry=self._telemetry(
                    request=request,
                    started=started,
                    output_summary={"missing": len(missing)},
                ),
                artifacts=(),
            )

        validation = self.adapter.validate(request)
        return CapabilityResult(
            capability_name="index.validate",
            ok=True,
            output=validation,
            error=None,
            telemetry=self._telemetry(
                request=request,
                started=started,
                output_summary={
                    "artifact_count": len(request.artifact_paths),
                    "freshness": validation.freshness.status,
                },
            ),
            artifacts=(),
        )

    @staticmethod
    def _telemetry(
        *,
        request: IndexRequest,
        started: float,
        output_summary: dict[str, object],
    ) -> CapabilityTelemetry:
        return CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=int((perf_counter() - started) * 1000),
            input_summary={"workspace_root": request.workspace_root, "mode": request.mode},
            output_summary=output_summary,
            token_usage={},
            model_usage={},
            degraded=False,
            degradation_reason=None,
        )
