import hashlib

from homllm.common.types import Intent
from homllm.retrieval.interfaces import RetrievalResult

from homllm_v4.contracts.evidence import (
    EvidenceCandidate,
    EvidenceRetrievalRequest,
    EvidenceSet,
    RetrievalDiagnostics,
)


class V3RetrievalAdapter:
    """Compatibility boundary for homllm.retrieval."""

    def __init__(self, *, pipeline: object) -> None:
        self.pipeline = pipeline

    def retrieve(self, request: EvidenceRetrievalRequest) -> EvidenceSet:
        result = self.pipeline.retrieve(
            request.query,
            self._intent_from_policy(request.policy),
            self._top_k_from_policy(request.policy),
        )
        return self._to_evidence_set(request, result)

    def _to_evidence_set(
        self,
        request: EvidenceRetrievalRequest,
        result: RetrievalResult,
    ) -> EvidenceSet:
        metadata = dict(result.metadata or {})
        candidates = tuple(
            self._to_candidate(candidate)
            for candidate in result.candidates
        )
        return EvidenceSet(
            evidence_set_id=str(result.query_id),
            query=request.query,
            candidates=candidates,
            diagnostics=RetrievalDiagnostics(
                bm25_count=int(metadata.get("bm25_count") or 0),
                vector_count=int(metadata.get("vector_count") or 0),
                graph_added_count=int(metadata.get("graph_added_count") or 0),
                precision_added_count=int(metadata.get("precision_recovery_added") or 0),
                coverage_added_count=int(metadata.get("coverage_recovery_added") or 0),
                retrieval_disagreement=self._optional_float(
                    metadata.get("retrieval_disagreement")
                ),
                degraded=bool(metadata.get("error")),
                degradation_reason=str(metadata["error"]) if metadata.get("error") else None,
            ),
        )

    def _to_candidate(self, candidate: object) -> EvidenceCandidate:
        content = str(getattr(candidate, "content", "") or "")
        return EvidenceCandidate(
            candidate_id=str(getattr(candidate, "doc_id")),
            file_path=str(getattr(candidate, "file", "")),
            symbol_id=getattr(candidate, "symbol_id", None),
            span_start=getattr(candidate, "span_start", None),
            span_end=getattr(candidate, "span_end", None),
            content_hash=self._content_hash(content),
            source_channels=tuple(getattr(candidate, "provenance", ()) or ()),
            bm25_score=self._optional_float(getattr(candidate, "bm25_score", None)),
            vector_score=self._optional_float(getattr(candidate, "vector_score", None)),
            graph_score=self._optional_float(getattr(candidate, "graph_score", None)),
            retrieval_score=float(getattr(candidate, "hybrid_score", 0.0) or 0.0),
            metadata={
                "content": content,
                "granularity_level": getattr(candidate, "granularity_level", None),
                "parent_symbol_id": getattr(candidate, "parent_symbol_id", None),
                "entity_ids": tuple(getattr(candidate, "entity_ids", ()) or ()),
                "doc_type": getattr(candidate, "doc_type", None),
                "symbol_name": getattr(candidate, "symbol_name", None),
            },
        )

    @staticmethod
    def _intent_from_policy(policy: dict[str, object]) -> Intent:
        raw = str(policy.get("intent", "UNKNOWN")).strip()
        normalized = raw.lower()
        for intent in Intent:
            if normalized in {intent.value, intent.name.lower()}:
                return intent
        return Intent.UNKNOWN

    @staticmethod
    def _top_k_from_policy(policy: dict[str, object]) -> int:
        return max(1, int(policy.get("top_k", 50)))

    @staticmethod
    def _content_hash(content: str) -> str:
        normalized = content.replace("\r\n", "\n").encode("utf-8")
        return hashlib.sha256(normalized).hexdigest()

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if value is None:
            return None
        return float(value)
