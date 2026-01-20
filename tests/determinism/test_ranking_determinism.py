"""Determinism tests for Ranking layer."""

import pytest

from homllm.common.types import Intent
from homllm.ranking.interfaces import RankConfig, RankingInput
from homllm.ranking.pipeline import RankingPipeline
from homllm.retrieval.interfaces import Candidate


@pytest.fixture
def test_config() -> RankConfig:
    """Create test configuration."""
    return RankConfig(
        reranker_enabled=False,  # Disable for determinism test
        reranker_model="Qwen3-Reranker-0.6B",
        reranker_top_m=40,
        w_base=0.4,
        w_rerank=0.55,
        w_struct=0.05,
        w_bm25=0.4,
        w_dense=0.4,
        w_name=0.2,
    )


@pytest.fixture
def test_candidates() -> list[Candidate]:
    """Create test candidates."""
    return [
        Candidate(
            doc_id="doc1",
            file="file1.py",
            symbol_id="func1",
            content="def func1(): pass",
            bm25_score=0.8,
            vector_score=0.7,
            hybrid_score=0.75,
            provenance=("bm25", "vector"),
        ),
        Candidate(
            doc_id="doc2",
            file="file2.py",
            symbol_id="func2",
            content="def func2(): pass",
            bm25_score=0.6,
            vector_score=0.8,
            hybrid_score=0.7,
            provenance=("vector",),
        ),
    ]


def test_ranking_determinism(
    test_config: RankConfig, test_candidates: list[Candidate]
):
    """
    Test that Ranking produces identical results for same inputs.
    
    RNK-001: Same inputs → same ranking
    """
    pipeline = RankingPipeline(test_config)

    input_data = RankingInput(
        query="find function",
        candidates=tuple(test_candidates),
        config=test_config,
    )

    # Run ranking twice
    result1 = pipeline.rank(input_data)
    result2 = pipeline.rank(input_data)

    # Results should be identical
    assert len(result1.ranked_candidates) == len(result2.ranked_candidates)

    # Candidate order should be identical
    for c1, c2 in zip(result1.ranked_candidates, result2.ranked_candidates):
        assert c1.doc_id == c2.doc_id
        assert c1.hybrid_score == c2.hybrid_score

    # Debug traces should match
    assert len(result1.debug_traces) == len(result2.debug_traces)
    for t1, t2 in zip(result1.debug_traces, result2.debug_traces):
        assert t1.final_score == t2.final_score
        assert t1.candidate_id == t2.candidate_id
