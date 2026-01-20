"""Determinism tests for Context layer."""

import pytest

from homllm.context.interfaces import ContextConfig
from homllm.context.pipeline import ContextPipeline
from homllm.ranking.interfaces import DebugTrace, FeatureVector, RankMetadata, RankingOutput
from homllm.retrieval.interfaces import Candidate


@pytest.fixture
def test_config() -> ContextConfig:
    """Create test configuration."""
    return ContextConfig(
        max_tokens=4000,
        budget_mode="adaptive",
        summarization_enabled=False,
        ordering="structural_first",
        structural_priority_multiplier=1.5,
    )


@pytest.fixture
def test_ranking_output() -> RankingOutput:
    """Create test ranking output."""
    candidates = [
        Candidate(
            doc_id="doc1",
            file="file1.py",
            symbol_id="func1",
            content="def func1():\n    pass\n",
            bm25_score=0.8,
            vector_score=0.7,
            hybrid_score=0.75,
            provenance=("bm25", "vector"),
        ),
    ]

    debug_traces = [
        DebugTrace(
            candidate_id="doc1",
            base_score=0.7,
            rerank_score=0.8,
            struct_bonus=0.05,
            final_score=0.75,
            features=FeatureVector(
                bm25_percentile=0.8,
                dense_percentile=0.7,
                name_match_score=0.5,
                is_entrypoint=False,
                has_decorator=False,
                callgraph_distance=0.0,
            ),
            provenance=("bm25", "vector"),
        ),
    ]

    return RankingOutput(
        ranked_candidates=tuple(candidates),
        debug_traces=tuple(debug_traces),
        metadata=RankMetadata(
            latency_ms=10,
            reranker_used=True,
            reranker_unavailable=False,
            candidate_count=1,
        ),
    )


def test_context_determinism(
    test_config: ContextConfig, test_ranking_output: RankingOutput
):
    """
    Test that Context produces identical artifacts for same inputs.
    
    CTX-001: Same inputs + config → same context artifact
    """
    pipeline = ContextPipeline(test_config)

    query = "find function"

    # Run assembly twice
    result1 = pipeline.assemble(test_ranking_output, query, query_id="test-1")
    result2 = pipeline.assemble(test_ranking_output, query, query_id="test-1")

    # Results should be identical (except query_id which we control)
    assert result1.context_text == result2.context_text
    assert len(result1.blocks) == len(result2.blocks)
    assert result1.used_tokens == result2.used_tokens
    assert result1.token_budget == result2.token_budget

    # Block order should be identical
    for b1, b2 in zip(result1.blocks, result2.blocks):
        assert b1.block_id == b2.block_id
        assert b1.file == b2.file
        assert b1.start_line == b2.start_line
