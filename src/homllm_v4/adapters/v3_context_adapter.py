from homllm.context.interfaces import ContextArtifact
from homllm.ranking.interfaces import DebugTrace, RankMetadata, RankingOutput

from homllm_v4.adapters.v3_ranking_adapter import V3RankingAdapter
from homllm_v4.contracts.context import ContextBlock, ContextPack, ContextPackRequest


class V3ContextAdapter:
    """Compatibility boundary for homllm.context."""

    def __init__(self, *, pipeline: object) -> None:
        self.pipeline = pipeline

    def build(self, request: ContextPackRequest) -> ContextPack:
        artifact = self.pipeline.assemble(
            self._to_v3_ranking_output(request),
            request.query,
            query_id=request.ranked_evidence_set.ranked_set_id,
            unresolved_claim_hints=list(
                request.policy.get("unresolved_claim_hints", []) or []
            ),
        )
        return self._to_context_pack(request, artifact)

    @staticmethod
    def _to_v3_ranking_output(request: ContextPackRequest) -> RankingOutput:
        candidates = tuple(
            V3RankingAdapter._to_v3_candidate(item.candidate)
            for item in request.ranked_evidence_set.items
        )
        traces = tuple(
            DebugTrace(
                candidate_id=item.candidate.candidate_id,
                base_score=float(item.score_components.get("base", 0.0)),
                rerank_score=float(item.score_components.get("rerank", 0.0)),
                struct_bonus=float(item.score_components.get("struct", 0.0)),
                final_score=float(item.final_score),
                features=None,
                provenance=tuple(item.candidate.source_channels),
                rerank_evaluated=bool(item.reranked),
            )
            for item in request.ranked_evidence_set.items
        )
        return RankingOutput(
            ranked_candidates=candidates,
            debug_traces=traces,
            metadata=RankMetadata(
                latency_ms=0,
                reranker_used=request.ranked_evidence_set.diagnostics.reranker_used,
                reranker_unavailable=not request.ranked_evidence_set.diagnostics.reranker_available,
                candidate_count=len(candidates),
            ),
        )

    @staticmethod
    def _to_context_pack(
        request: ContextPackRequest,
        artifact: ContextArtifact,
    ) -> ContextPack:
        return ContextPack(
            context_pack_id=str(artifact.query_id),
            purpose="answer",
            text=artifact.context_text,
            blocks=tuple(
                ContextBlock(
                    block_id=block.block_id,
                    candidate_id=block.block_id,
                    file_path=block.file,
                    span_start=block.start_line,
                    span_end=block.end_line,
                    text=block.content,
                    token_count=len(block.content.split()),
                    score=_score_for_block(request, block.block_id),
                    citation=f"{block.file}:{block.start_line}-{block.end_line}",
                )
                for block in artifact.blocks
            ),
            used_tokens=int(artifact.used_tokens),
            dropped_candidates=tuple(),
            diagnostics={
                "token_budget": artifact.token_budget,
                "provenance": artifact.provenance,
                "explain_trace": tuple(artifact.explain_trace),
            },
        )


def _score_for_block(request: ContextPackRequest, block_id: str) -> float:
    for item in request.ranked_evidence_set.items:
        if item.candidate.candidate_id == block_id:
            return float(item.final_score)
    return 0.0
