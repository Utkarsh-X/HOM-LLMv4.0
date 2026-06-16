from collections import Counter

from homllm.ranking.interfaces import RankConfig, RankingInput, RankingOutput
from homllm.retrieval.interfaces import Candidate

from homllm_v4.contracts.evidence import EvidenceCandidate
from homllm_v4.contracts.ranking import (
    EvidenceRankingRequest,
    RankedEvidence,
    RankedEvidenceSet,
    RankingDiagnostics,
)


class V3RankingAdapter:
    """Compatibility boundary for homllm.ranking."""

    def __init__(self, *, pipeline: object) -> None:
        self.pipeline = pipeline

    def rank(self, request: EvidenceRankingRequest) -> RankedEvidenceSet:
        output = self.pipeline.rank(
            RankingInput(
                query=request.evidence_set.query,
                candidates=tuple(
                    self._to_v3_candidate(candidate)
                    for candidate in request.evidence_set.candidates
                ),
                config=self._rank_config_from_policy(request.policy),
            )
        )
        return self._to_ranked_set(request, output)

    def _to_ranked_set(
        self,
        request: EvidenceRankingRequest,
        output: RankingOutput,
    ) -> RankedEvidenceSet:
        evidence_by_id = {
            candidate.candidate_id: candidate
            for candidate in request.evidence_set.candidates
        }
        trace_by_id = {
            trace.candidate_id: trace
            for trace in output.debug_traces
        }
        ranked_items: list[RankedEvidence] = []
        for index, candidate in enumerate(output.ranked_candidates, start=1):
            evidence_candidate = evidence_by_id.get(str(candidate.doc_id))
            if evidence_candidate is None:
                evidence_candidate = self._from_v3_candidate(candidate)
            trace = trace_by_id.get(str(candidate.doc_id))
            ranked_items.append(
                RankedEvidence(
                    candidate=evidence_candidate,
                    rank=index,
                    final_score=float(
                        getattr(trace, "final_score", getattr(candidate, "hybrid_score", 0.0))
                    ),
                    score_components={
                        "base": float(getattr(trace, "base_score", 0.0) if trace else 0.0),
                        "rerank": float(getattr(trace, "rerank_score", 0.0) if trace else 0.0),
                        "struct": float(getattr(trace, "struct_bonus", 0.0) if trace else 0.0),
                    },
                    reranked=bool(getattr(trace, "rerank_evaluated", False) if trace else False),
                )
            )

        metadata = output.metadata
        concentration = metadata.ranking_concentration or {}
        geometry = metadata.ranking_geometry or {}
        return RankedEvidenceSet(
            ranked_set_id=f"{request.evidence_set.evidence_set_id}:ranked",
            items=tuple(ranked_items),
            diagnostics=RankingDiagnostics(
                reranker_used=bool(metadata.reranker_used),
                reranker_available=not bool(metadata.reranker_unavailable),
                reranker_degraded_reason=(
                    "reranker_unavailable" if metadata.reranker_unavailable else None
                ),
                concentration_ratio=self._optional_float(
                    concentration.get("max_file_block_ratio")
                ),
                score_separation=self._optional_float(geometry.get("score_separation")),
                top_source_channels=dict(
                    Counter(
                        channel
                        for item in ranked_items
                        for channel in item.candidate.source_channels
                    )
                ),
            ),
        )

    @staticmethod
    def _to_v3_candidate(candidate: EvidenceCandidate) -> Candidate:
        return Candidate(
            doc_id=candidate.candidate_id,
            file=candidate.file_path,
            symbol_id=candidate.symbol_id,
            content=str(candidate.metadata.get("content", "")),
            bm25_score=float(candidate.bm25_score or 0.0),
            vector_score=float(candidate.vector_score or 0.0),
            hybrid_score=float(candidate.retrieval_score),
            provenance=tuple(candidate.source_channels),
            granularity_level=candidate.metadata.get("granularity_level"),
            span_start=candidate.span_start,
            span_end=candidate.span_end,
            parent_symbol_id=candidate.metadata.get("parent_symbol_id"),
            entity_ids=tuple(candidate.metadata.get("entity_ids", ()) or ()),
            doc_type=candidate.metadata.get("doc_type"),
            symbol_name=candidate.metadata.get("symbol_name"),
        )

    @staticmethod
    def _from_v3_candidate(candidate: Candidate) -> EvidenceCandidate:
        return EvidenceCandidate(
            candidate_id=str(candidate.doc_id),
            file_path=str(candidate.file),
            symbol_id=candidate.symbol_id,
            span_start=candidate.span_start,
            span_end=candidate.span_end,
            content_hash="",
            source_channels=tuple(candidate.provenance),
            bm25_score=float(candidate.bm25_score),
            vector_score=float(candidate.vector_score),
            graph_score=None,
            retrieval_score=float(candidate.hybrid_score),
            metadata={"content": candidate.content},
        )

    @staticmethod
    def _rank_config_from_policy(policy: dict[str, object]) -> RankConfig:
        v3_config = policy.get("v3_config")
        if isinstance(v3_config, RankConfig):
            return v3_config
        return RankConfig(
            reranker_enabled=bool(policy.get("reranker_enabled", False)),
            reranker_model=str(policy.get("reranker_model", "Qwen/Qwen3-Reranker-0.6B")),
            reranker_top_m=int(policy.get("reranker_top_m", 35)),
            w_base=float(policy.get("w_base", 1.0)),
            w_rerank=float(policy.get("w_rerank", 0.32)),
            w_struct=float(policy.get("w_struct", 0.05)),
            w_bm25=float(policy.get("w_bm25", 0.4)),
            w_dense=float(policy.get("w_dense", 0.4)),
            w_name=float(policy.get("w_name", 0.2)),
        )

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if value is None:
            return None
        return float(value)
