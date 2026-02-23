"""Determinism and authority-lock tests for context ordering."""

import pytest

from homllm.context.interfaces import AllocatedBlock, ContextConfig
from homllm.context.pipeline import ContextPipeline
from homllm.ranking.interfaces import DebugTrace, FeatureVector, RankMetadata, RankingOutput
from homllm.retrieval.interfaces import Candidate


def _make_ranking_output() -> RankingOutput:
    candidates = [
        Candidate(
            doc_id="doc_a",
            file="z_file.py",
            symbol_id="sym_a",
            content="def a():\n    return 1\n",
            bm25_score=0.8,
            vector_score=0.7,
            hybrid_score=0.75,
            provenance=("bm25",),
        ),
        Candidate(
            doc_id="doc_b",
            file="a_file.py",
            symbol_id="sym_b",
            content="@decorator\ndef b():\n    return 2\n",
            bm25_score=0.7,
            vector_score=0.6,
            hybrid_score=0.65,
            provenance=("expansion:decorator",),
        ),
    ]
    traces = [
        DebugTrace(
            candidate_id="doc_a",
            base_score=0.7,
            rerank_score=0.8,
            struct_bonus=0.0,
            final_score=0.8,
            features=FeatureVector(
                bm25_percentile=0.8,
                dense_percentile=0.7,
                name_match_score=0.1,
                is_entrypoint=False,
                has_decorator=False,
                callgraph_distance=0.0,
            ),
            provenance=("bm25",),
        ),
        DebugTrace(
            candidate_id="doc_b",
            base_score=0.6,
            rerank_score=0.7,
            struct_bonus=0.1,
            final_score=0.7,
            features=FeatureVector(
                bm25_percentile=0.7,
                dense_percentile=0.6,
                name_match_score=0.1,
                is_entrypoint=False,
                has_decorator=True,
                callgraph_distance=0.0,
            ),
            provenance=("vector",),
        ),
    ]
    return RankingOutput(
        ranked_candidates=tuple(candidates),
        debug_traces=tuple(traces),
        metadata=RankMetadata(
            latency_ms=1,
            reranker_used=True,
            reranker_unavailable=False,
            candidate_count=2,
        ),
    )


def test_context_authority_lock_preserves_ranking_order():
    pipeline = ContextPipeline(
        ContextConfig(
            max_tokens=4000,
            budget_mode="adaptive",
            summarization_enabled=False,
            ordering="structural_first",
            ranking_surface_lock_enabled=True,
        )
    )
    output = pipeline.assemble(_make_ranking_output(), "query", query_id="q1")
    assert [b.block_id for b in output.blocks] == ["doc_a", "doc_b"]
    assert output.provenance["ranking_surface_lock_enabled"] is True
    assert output.provenance["ranking_order_preserved"] is True
    assert output.provenance["context_reorder_count"] == 0


def test_context_authority_lock_hard_fails_on_reorder():
    pipeline = ContextPipeline(
        ContextConfig(
            max_tokens=4000,
            budget_mode="adaptive",
            summarization_enabled=False,
            ordering="score_first",
            ranking_surface_lock_enabled=True,
        )
    )

    def _reversing_allocate(blocks, *_args, **_kwargs):
        return [
            AllocatedBlock(
                block=sb.block,
                allocated_tokens=max(1, len(sb.block.content) // 4),
                truncated_content=sb.block.content,
            )
            for sb in reversed(blocks)
        ]

    pipeline.budget_manager.allocate = _reversing_allocate
    with pytest.raises(RuntimeError, match="RANKING_AUTHORITY_LOCK_VIOLATION"):
        pipeline.assemble(_make_ranking_output(), "query", query_id="q2")
