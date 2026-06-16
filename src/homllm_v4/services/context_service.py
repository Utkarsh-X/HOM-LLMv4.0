from time import perf_counter

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.context import ContextPack, ContextPackRequest
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.telemetry import CapabilityTelemetry


class ContextPackService:
    def __init__(self, adapter: object | None = None) -> None:
        self.adapter = adapter

    def build(self, request: ContextPackRequest) -> CapabilityResult[ContextPack]:
        if self.adapter is None:
            raise NotImplementedError("adapter-backed context build requires an adapter")
        started = perf_counter()
        try:
            context_pack = self.adapter.build(request)
        except Exception as exc:
            return CapabilityResult(
                capability_name="context.build",
                ok=False,
                output=None,
                error=CapabilityError(
                    code="adapter_failed",
                    message=str(exc),
                    recoverable=True,
                    retryable=False,
                    details={"adapter": type(self.adapter).__name__},
                ),
                telemetry=self._telemetry(request, started, {"error": type(exc).__name__}),
                artifacts=(),
            )
        return CapabilityResult(
            capability_name="context.build",
            ok=True,
            output=context_pack,
            error=None,
            telemetry=self._telemetry(
                request,
                started,
                {"block_count": len(context_pack.blocks), "used_tokens": context_pack.used_tokens},
            ),
            artifacts=(),
        )

    @staticmethod
    def _telemetry(
        request: ContextPackRequest,
        started: float,
        output_summary: dict[str, object],
    ) -> CapabilityTelemetry:
        return CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=int((perf_counter() - started) * 1000),
            input_summary={
                "task_id": request.task_id,
                "ranked_set_id": request.ranked_evidence_set.ranked_set_id,
            },
            output_summary=output_summary,
            token_usage={},
            model_usage={},
            degraded=False,
            degradation_reason=None,
        )
