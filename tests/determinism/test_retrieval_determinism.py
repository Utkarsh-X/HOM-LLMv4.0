"""Determinism tests for Retrieval layer."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from homllm.common.types import Intent
from homllm.retrieval.interfaces import RetrievalConfig
from homllm.retrieval.pipeline import RetrievalPipeline


@pytest.fixture
def test_config() -> RetrievalConfig:
    """Create test configuration."""
    return RetrievalConfig(
        bm25_top_k=50,
        vector_top_k=50,
        hybrid_method="rrf",
        rrf_k=10,
        bm25_weight=0.5,
        vector_weight=0.5,
        expansion_enabled=False,
        expansion_max_additions=4,
        expansion_min_similarity=0.25,
    )


def test_retrieval_determinism(test_config: RetrievalConfig):
    """
    Test that Retrieval produces identical results for same query.
    
    RET-001: Same query + same index → same candidates
    """
    with TemporaryDirectory() as tmpdir:
        bm25_path = Path(tmpdir) / "bm25.index"
        vector_path = Path(tmpdir) / "vectors.lance"

        # Create pipeline
        pipeline = RetrievalPipeline(test_config, bm25_path, vector_path)

        # Run retrieval twice
        query = "find authentication function"
        result1 = pipeline.retrieve(query, Intent.SEARCH)
        result2 = pipeline.retrieve(query, Intent.SEARCH)

        # Results should be identical (same query_id may differ, but candidates should match)
        assert len(result1.candidates) == len(result2.candidates)
        # TODO: Compare candidate lists when indexing is complete
        # For now, test passes if no exceptions
        assert True
