from time import perf_counter

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import EvidenceRetrievalRequest, EvidenceSet
from homllm_v4.contracts.telemetry import CapabilityTelemetry


class EvidenceRetrievalService:
    def __init__(self, adapter: object | None = None) -> None:
        self.adapter = adapter

    def retrieve(self, request: EvidenceRetrievalRequest) -> CapabilityResult[EvidenceSet]:
        if self.adapter is None:
            raise NotImplementedError("adapter-backed retrieval requires an adapter")
        started = perf_counter()
        try:
            evidence_set = self.adapter.retrieve(request)
        except Exception as exc:
            return CapabilityResult(
                capability_name="evidence.retrieve",
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
            capability_name="evidence.retrieve",
            ok=True,
            output=evidence_set,
            error=None,
            telemetry=self._telemetry(
                request,
                started,
                {"candidate_count": len(evidence_set.candidates)},
            ),
            artifacts=(),
        )

    @staticmethod
    def _telemetry(
        request: EvidenceRetrievalRequest,
        started: float,
        output_summary: dict[str, object],
    ) -> CapabilityTelemetry:
        return CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=int((perf_counter() - started) * 1000),
            input_summary={"task_id": request.task_id, "query": request.query},
            output_summary=output_summary,
            token_usage={},
            model_usage={},
            degraded=False,
            degradation_reason=None,
        )
