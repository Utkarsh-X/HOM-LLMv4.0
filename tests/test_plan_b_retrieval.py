"""Unit tests for Plan B: Retrieval Layer Activation.

Tests cover:
- Diversity-aware MMR
- Intent-driven granularity boosting
- Graph stitch expansion
- Legacy index detection
- RetrievalConfig Plan B fields
"""

import pytest
from pathlib import Path

# Test imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from homllm.common.types import Intent
from homllm.retrieval.interfaces import Candidate, RetrievalConfig


class TestRetrievalConfigPlanB:
    """Tests for Plan B RetrievalConfig extensions."""

    def test_plan_b_defaults(self):
        """Test that Plan B defaults are set correctly."""
        config = RetrievalConfig(
            bm25_top_k=50,
            vector_top_k=50,
            hybrid_method="rrf",
            rrf_k=10,
            bm25_weight=0.5,
            vector_weight=0.5,
            expansion_enabled=True,
            expansion_max_additions=4,
            expansion_min_similarity=0.25,
        )
        
        # Plan B master toggle
        assert config.plan_b_enabled is True
        
        # Diversity MMR
        assert config.diversity_mmr_enabled is True
        assert config.mmr_lambda == 0.6
        assert config.mmr_similarity_threshold == 0.85
        
        # Granularity boost
        assert config.granularity_boost_enabled is True
        assert "EXPLANATORY" in config.granularity_boost_table
        assert "IMPLEMENTATION" in config.granularity_boost_table
        
        # Graph stitch
        assert config.graph_stitch_enabled is True
        assert config.graph_stitch_max_depth == 2
        assert config.graph_stitch_max_additions == 8
        assert config.graph_stitch_min_confidence == 0.5
        assert "calls" in config.graph_stitch_relation_priority

    def test_granularity_boost_table_populated(self):
        """Test that granularity boost table has correct structure."""
        config = RetrievalConfig(
            bm25_top_k=50,
            vector_top_k=50,
            hybrid_method="rrf",
            rrf_k=10,
            bm25_weight=0.5,
            vector_weight=0.5,
            expansion_enabled=True,
            expansion_max_additions=4,
            expansion_min_similarity=0.25,
        )
        
        # Check EXPLANATORY boosts coarse > medium > fine
        assert config.granularity_boost_table["EXPLANATORY"]["coarse"] == 2.0
        assert config.granularity_boost_table["EXPLANATORY"]["medium"] == 1.5
        assert config.granularity_boost_table["EXPLANATORY"]["fine"] == 1.0
        
        # Check IMPLEMENTATION boosts fine > medium > coarse
        assert config.granularity_boost_table["IMPLEMENTATION"]["fine"] == 2.0
        assert config.granularity_boost_table["IMPLEMENTATION"]["coarse"] == 0.8


class TestCandidateGranularity:
    """Tests for Candidate granularity_level field."""

    def test_candidate_granularity_level(self):
        """Test that Candidate has granularity_level field."""
        candidate = Candidate(
            doc_id="test123",
            file="test.py",
            symbol_id="func1",
            content="def test(): pass",
            granularity_level="fine",
        )
        
        assert candidate.granularity_level == "fine"

    def test_candidate_granularity_default_none(self):
        """Test that granularity_level defaults to None."""
        candidate = Candidate(
            doc_id="test123",
            file="test.py",
            symbol_id="func1",
            content="def test(): pass",
        )
        
        assert candidate.granularity_level is None


class TestDiversityMMR:
    """Tests for diversity-aware MMR."""

    def test_apply_mmr_empty_candidates(self):
        """Test MMR with empty candidates list."""
        from homllm.retrieval.diversity_mmr import apply_mmr
        
        result = apply_mmr([], {}, 0.6, 0.85)
        assert result == []

    def test_apply_mmr_single_candidate(self):
        """Test MMR with single candidate (no change)."""
        from homllm.retrieval.diversity_mmr import apply_mmr
        
        candidate = Candidate(
            doc_id="test1",
            file="test.py",
            symbol_id="func1",
            content="def test(): pass",
            hybrid_score=1.0,
        )
        
        result = apply_mmr([candidate], {}, 0.6, 0.85)
        assert len(result) == 1
        assert result[0].doc_id == "test1"

    def test_apply_mmr_deterministic(self):
        """Test that MMR is deterministic."""
        from homllm.retrieval.diversity_mmr import apply_mmr
        import numpy as np
        
        candidates = [
            Candidate(
                doc_id=f"test{i}",
                file="test.py",
                symbol_id=f"func{i}",
                content=f"def test{i}(): pass",
                hybrid_score=1.0 - (i * 0.1),
            )
            for i in range(5)
        ]
        
        # Create simple embeddings
        embeddings = {
            c.doc_id: tuple(np.random.RandomState(hash(c.doc_id) % 2**32).rand(10))
            for c in candidates
        }
        
        result1 = apply_mmr(candidates, embeddings, 0.6, 0.85)
        result2 = apply_mmr(candidates, embeddings, 0.6, 0.85)
        
        # Same input → same output
        assert [r.doc_id for r in result1] == [r.doc_id for r in result2]


class TestGranularityBooster:
    """Tests for intent-driven granularity boosting."""

    def test_apply_granularity_boost_empty(self):
        """Test boost with empty candidates."""
        from homllm.retrieval.granularity_booster import apply_granularity_boost
        
        result = apply_granularity_boost([], Intent.IMPLEMENT)
        assert result == []

    def test_apply_granularity_boost_no_metadata(self):
        """Test boost silently skips candidates without granularity."""
        from homllm.retrieval.granularity_booster import apply_granularity_boost
        
        candidates = [
            Candidate(
                doc_id="test1",
                file="test.py",
                symbol_id="func1",
                content="def test(): pass",
                hybrid_score=1.0,
            )
        ]
        
        result = apply_granularity_boost(candidates, Intent.IMPLEMENT)
        
        # No granularity lookup → unchanged
        assert len(result) == 1
        assert result[0].hybrid_score == 1.0

    def test_apply_granularity_boost_with_lookup(self):
        """Test boost applies when granularity metadata available."""
        from homllm.retrieval.granularity_booster import apply_granularity_boost
        
        candidates = [
            Candidate(
                doc_id="test1",
                file="test.py",
                symbol_id="func1",
                content="def test(): pass",
                hybrid_score=1.0,
            )
        ]
        
        lookup = {"test1": "fine"}
        
        result = apply_granularity_boost(
            candidates,
            Intent.IMPLEMENT,  # fine = 2.0 boost
            granularity_lookup=lookup,
        )
        
        assert len(result) == 1
        assert result[0].hybrid_score == 2.0  # 1.0 * 2.0
        assert result[0].granularity_level == "fine"


class TestGraphStitch:
    """Tests for graph-based structural expansion."""

    def test_graph_stitch_config_defaults(self):
        """Test GraphStitchConfig defaults."""
        from homllm.retrieval.graph_stitch import GraphStitchConfig
        
        config = GraphStitchConfig()
        
        assert config.enabled is True
        assert config.max_depth == 2
        assert config.max_additions == 8
        assert config.min_confidence == 0.5
        assert "calls" in config.relation_priority
        assert "inherits" in config.relation_priority

    def test_graph_stitch_expander_no_duckdb(self):
        """Test GraphStitchExpander without DuckDB returns unchanged."""
        from homllm.retrieval.graph_stitch import GraphStitchExpander
        
        expander = GraphStitchExpander(duckdb_path=None)
        
        candidates = [
            Candidate(
                doc_id="test1",
                file="test.py",
                symbol_id="func1",
                content="def test(): pass",
            )
        ]
        
        result = expander.expand(candidates, "test query")
        
        # No DuckDB → unchanged
        assert result == candidates


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
