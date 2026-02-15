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
from collections import defaultdict
from types import SimpleNamespace

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
        assert config.graph_stitch_relation_priority[0] == "resolves_to"

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

    def test_granularity_mixing_profiles_default_populated(self):
        """Granularity mixing defaults should be deterministic and complete."""
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

        assert "UNKNOWN" in config.granularity_mixing_profiles
        assert "EXPLAIN" in config.granularity_mixing_profiles
        assert config.granularity_mixing_profiles["EXPLAIN"]["fine"]["min"] == 3
        assert config.granularity_mixing_profiles["EXPLAIN"]["fine"]["max"] == 8

    def test_granularity_mixing_profiles_invalid_range_fails(self):
        """Misconfigured granularity ranges must fail fast."""
        with pytest.raises(ValueError, match="min cannot exceed max"):
            RetrievalConfig(
                bm25_top_k=50,
                vector_top_k=50,
                hybrid_method="rrf",
                rrf_k=10,
                bm25_weight=0.5,
                vector_weight=0.5,
                expansion_enabled=True,
                expansion_max_additions=4,
                expansion_min_similarity=0.25,
                granularity_mixing_profiles={
                    "UNKNOWN": {
                        "fine": {"min": 2, "max": 1},
                        "medium": {"min": 0, "max": 1},
                        "coarse": {"min": 0, "max": 1},
                    }
                },
            )

    def test_query_expansion_defaults_present(self):
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
        assert config.query_expansion_enabled is True
        assert config.query_expansion_max_terms == 6
        assert "auth" in config.query_expansion_synonyms

    def test_query_expansion_synonyms_invalid_shape_fails(self):
        with pytest.raises(ValueError, match="query_expansion.synonyms"):
            RetrievalConfig(
                bm25_top_k=50,
                vector_top_k=50,
                hybrid_method="rrf",
                rrf_k=10,
                bm25_weight=0.5,
                vector_weight=0.5,
                expansion_enabled=True,
                expansion_max_additions=4,
                expansion_min_similarity=0.25,
                query_expansion_synonyms={"auth": "authentication"},
            )


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
        assert config.relation_priority[0] == "resolves_to"
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

    def test_graph_stitch_cache_relations_are_sorted_deterministically(self):
        """Cache-backed relation fetch should have deterministic tie ordering."""
        from homllm.retrieval.graph_stitch import GraphStitchExpander, GraphStitchConfig

        expander = GraphStitchExpander(
            duckdb_path=None,
            config=GraphStitchConfig(graph_cache_enabled=True),
        )
        expander._graph_topology = SimpleNamespace(
            adjacency={
                "seed": [
                    ("z_entity", "CALLS", 1.0),
                    ("a_entity", "CALLS", 1.0),
                    ("m_entity", "USES", 0.9),
                ]
            }
        )

        rows = expander._get_relations_from("seed")
        assert [r["dst_entity_id"] for r in rows] == ["a_entity", "z_entity", "m_entity"]

    def test_graph_stitch_bfs_seed_and_tie_order_deterministic(self):
        """BFS should be deterministic for set seed input and confidence ties."""
        from homllm.retrieval.graph_stitch import GraphStitchExpander, GraphStitchConfig

        expander = GraphStitchExpander(
            duckdb_path=None,
            config=GraphStitchConfig(max_depth=2, beam_high=8, beam_low=8),
        )

        relation_map = {
            "seed_a": [
                {"dst_entity_id": "n2", "relation_type": "CALLS", "confidence": 0.8},
                {"dst_entity_id": "n1", "relation_type": "CALLS", "confidence": 0.8},
            ],
            "seed_b": [
                {"dst_entity_id": "n4", "relation_type": "USES", "confidence": 0.5},
                {"dst_entity_id": "n3", "relation_type": "USES", "confidence": 0.5},
            ],
            "n1": [],
            "n2": [],
            "n3": [],
            "n4": [],
        }
        expander._get_relations_from = lambda entity_id: relation_map.get(entity_id, [])  # type: ignore[method-assign]

        first, *_ = expander._bfs_expand({"seed_b", "seed_a"}, defaultdict(lambda: {"high": 0, "low": 0, "total_before": 0, "after": 0}))
        second, *_ = expander._bfs_expand({"seed_a", "seed_b"}, defaultdict(lambda: {"high": 0, "low": 0, "total_before": 0, "after": 0}))

        first_key = [(e.src_entity_id, e.dst_entity_id, e.relation_type, e.hop) for e in first]
        second_key = [(e.src_entity_id, e.dst_entity_id, e.relation_type, e.hop) for e in second]
        assert first_key == second_key
        assert first_key == [
            ("seed_a", "n1", "CALLS", 1),
            ("seed_a", "n2", "CALLS", 1),
            ("seed_b", "n3", "USES", 1),
            ("seed_b", "n4", "USES", 1),
        ]

    def test_graph_stitch_expand_sorts_related_edges_deterministically(self):
        """expand() should normalize edge ordering even if BFS returns shuffled edges."""
        from homllm.retrieval.graph_stitch import GraphStitchExpander, GraphStitchConfig, RelationEdge

        expander = GraphStitchExpander(
            duckdb_path=None,
            config=GraphStitchConfig(enabled=True, max_additions=8, graph_cache_enabled=False),
        )
        expander._duckdb = object()  # bypass availability gate

        edge_a = RelationEdge("seed", "entity_b", "CALLS", 1, 0.7)
        edge_b = RelationEdge("seed", "entity_a", "CALLS", 1, 0.7)
        state = {"flip": False}

        def fake_bfs(seed_ids, hop_stats):
            state["flip"] = not state["flip"]
            edges = [edge_a, edge_b] if state["flip"] else [edge_b, edge_a]
            return edges, 2, 2, 2

        expander._bfs_expand = fake_bfs  # type: ignore[method-assign]
        expander._get_entity_info = lambda entity_id: {  # type: ignore[method-assign]
            "entity_type": "function",
            "name": entity_id,
            "file_path": "pkg/test.py",
            "span_start": 1,
            "span_end": 2,
            "confidence_score": 1.0,
            "granularity_level": "fine",
        }
        expander._get_entity_content = lambda entity_id, entity_info: f"def {entity_id}(): pass"  # type: ignore[method-assign]

        seed = Candidate(
            doc_id="seed_doc",
            file="pkg/test.py",
            symbol_id="seed",
            content="def seed(): pass",
        )

        out1 = expander.expand([seed], "test query")
        out2 = expander.expand([seed], "test query")

        added1 = [c.symbol_id for c in out1[1:]]
        added2 = [c.symbol_id for c in out2[1:]]
        assert added1 == added2 == ["entity_a", "entity_b"]


class TestRetrievalGapHelpers:
    """Tests for budgeting, dedup, and granularity mixing helpers."""

    def test_budget_selection_respects_effective_budget(self):
        from homllm.retrieval.budget import select_candidates_with_budget

        candidates = [
            Candidate(doc_id="a", file="a.py", symbol_id=None, content="x" * 900, hybrid_score=5.0),
            Candidate(doc_id="b", file="b.py", symbol_id=None, content="x" * 900, hybrid_score=4.0),
            Candidate(doc_id="c", file="c.py", symbol_id=None, content="x" * 900, hybrid_score=3.0),
        ]
        selected, tracker = select_candidates_with_budget(candidates, total_budget=600, reserve=200)
        assert len(selected) == 1
        assert tracker.used <= tracker.effective_budget

    def test_hierarchical_dedup_drops_parent_when_fine_present(self):
        from homllm.retrieval.deduplication import deduplicate_hierarchical

        candidates = [
            Candidate(doc_id="fine1", file="pkg/a.py", symbol_id=None, content="f", hybrid_score=5.0, granularity_level="fine"),
            Candidate(doc_id="fine2", file="pkg/a.py", symbol_id=None, content="f", hybrid_score=4.0, granularity_level="fine"),
            Candidate(doc_id="medium", file="pkg/a.py", symbol_id=None, content="m", hybrid_score=3.0, granularity_level="medium"),
            Candidate(doc_id="coarse", file="pkg/a.py", symbol_id=None, content="c", hybrid_score=2.0, granularity_level="coarse"),
        ]
        deduped = deduplicate_hierarchical(candidates)
        ids = {candidate.doc_id for candidate in deduped}
        assert "coarse" not in ids
        assert "medium" not in ids
        assert "fine1" in ids and "fine2" in ids

    def test_hierarchical_dedup_keeps_structural_context_for_explain(self):
        from homllm.retrieval.deduplication import deduplicate_hierarchical

        candidates = [
            Candidate(doc_id="fine1", file="pkg/a.py", symbol_id=None, content="f", hybrid_score=5.0, granularity_level="fine"),
            Candidate(doc_id="fine2", file="pkg/a.py", symbol_id=None, content="f", hybrid_score=4.5, granularity_level="fine"),
            Candidate(doc_id="medium1", file="pkg/a.py", symbol_id=None, content="m", hybrid_score=4.0, granularity_level="medium"),
            Candidate(doc_id="coarse1", file="pkg/a.py", symbol_id=None, content="c", hybrid_score=3.5, granularity_level="coarse"),
        ]
        deduped = deduplicate_hierarchical(candidates, intent=Intent.EXPLAIN)
        ids = {candidate.doc_id for candidate in deduped}
        assert "medium1" in ids
        assert "coarse1" in ids
        assert "fine1" in ids and "fine2" in ids

    def test_granularity_mix_prefers_explain_diversity(self):
        from homllm.retrieval.granularity_strategy import apply_granularity_mix

        candidates = [
            Candidate(doc_id="f1", file="a.py", symbol_id=None, content="f", hybrid_score=9.0, granularity_level="fine"),
            Candidate(doc_id="f2", file="a.py", symbol_id=None, content="f", hybrid_score=8.0, granularity_level="fine"),
            Candidate(doc_id="m1", file="a.py", symbol_id=None, content="m", hybrid_score=7.0, granularity_level="medium"),
            Candidate(doc_id="c1", file="a.py", symbol_id=None, content="c", hybrid_score=6.0, granularity_level="coarse"),
        ]
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
        mixed = apply_granularity_mix(
            candidates,
            Intent.EXPLAIN,
            config.granularity_mixing_profiles,
        )
        levels = {candidate.granularity_level for candidate in mixed[:4]}
        assert "fine" in levels
        assert "medium" in levels
        assert "coarse" in levels


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
