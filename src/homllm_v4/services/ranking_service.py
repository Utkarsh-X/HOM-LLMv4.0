from time import perf_counter

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.ranking import EvidenceRankingRequest, RankedEvidenceSet
from homllm_v4.contracts.telemetry import CapabilityTelemetry


class EvidenceRankingService:
    def __init__(self, adapter: object | None = None) -> None:
        self.adapter = adapter

    def rank(self, request: EvidenceRankingRequest) -> CapabilityResult[RankedEvidenceSet]:
        if self.adapter is None:
            raise NotImplementedError("adapter-backed ranking requires an adapter")
        started = perf_counter()
        try:
            ranked_set = self.adapter.rank(request)
        except Exception as exc:
            return CapabilityResult(
                capability_name="evidence.rank",
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
            capability_name="evidence.rank",
            ok=True,
            output=ranked_set,
            error=None,
            telemetry=self._telemetry(
                request,
                started,
                {"item_count": len(ranked_set.items)},
            ),
            artifacts=(),
        )

    @staticmethod
    def _telemetry(
        request: EvidenceRankingRequest,
        started: float,
        output_summary: dict[str, object],
    ) -> CapabilityTelemetry:
        return CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=int((perf_counter() - started) * 1000),
            input_summary={
                "task_id": request.task_id,
                "evidence_set_id": request.evidence_set.evidence_set_id,
            },
            output_summary=output_summary,
            token_usage={},
            model_usage={},
            degraded=False,
            degradation_reason=None,
        )
