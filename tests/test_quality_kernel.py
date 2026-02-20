"""
Unit tests for the Context Quality Evaluation Kernel.

Tests all 7 metrics with known inputs and expected outputs,
the PercentileWindow normalization engine, and the full kernel
integration with mock pipeline objects.
"""

import json
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from homllm.quality.metrics import (
    semantic_strength,
    query_term_recall,
    file_entropy,
    content_overlap,
    score_separation,
    reranker_influence,
    budget_utilization,
)
from homllm.quality.percentile import PercentileWindow, PercentileTracker
from homllm.quality.schema import MetricRecord, MetricStorage


# ===========================================================================
# M1 — Semantic Strength
# ===========================================================================


class TestSemanticStrength:
    def test_empty(self):
        assert semantic_strength([]) == 0.0

    def test_single(self):
        assert semantic_strength([0.8]) == 0.8

    def test_mean(self):
        scores = [0.9, 0.7, 0.5, 0.3]
        expected = sum(scores) / len(scores)
        assert abs(semantic_strength(scores) - expected) < 1e-9

    def test_all_zeros(self):
        assert semantic_strength([0.0, 0.0, 0.0]) == 0.0

    def test_all_ones(self):
        assert semantic_strength([1.0, 1.0, 1.0]) == 1.0


# ===========================================================================
# M2 — Query Term Recall
# ===========================================================================


class TestQueryTermRecall:
    def test_full_recall(self):
        query = "authentication middleware handler"
        blocks = ["authentication check middleware layer", "handler dispatch"]
        result = query_term_recall(query, blocks)
        assert result == 1.0

    def test_zero_recall(self):
        query = "authentication middleware"
        blocks = ["def unrelated_function(): pass"]
        result = query_term_recall(query, blocks)
        assert result == 0.0

    def test_partial_recall(self):
        query = "authentication middleware handler"
        blocks = ["authentication is important"]
        result = query_term_recall(query, blocks)
        # "authentication" is found, "middleware" and "handler" are not
        assert 0.0 < result < 1.0

    def test_empty_query(self):
        result = query_term_recall("", ["some content"])
        assert result == 0.0

    def test_empty_blocks(self):
        result = query_term_recall("some query", [])
        assert result == 0.0

    def test_stopwords_ignored(self):
        query = "the is of and"
        blocks = ["the is of and"]
        # All terms are stopwords → no meaningful query terms
        result = query_term_recall(query, blocks)
        assert result == 0.0


# ===========================================================================
# M3 — File Entropy
# ===========================================================================


class TestFileEntropy:
    def test_single_file(self):
        assert file_entropy(["a.py", "a.py", "a.py"]) == 0.0

    def test_perfect_distribution(self):
        # 4 blocks from 4 different files → max entropy → normalized = 1.0
        files = ["a.py", "b.py", "c.py", "d.py"]
        result = file_entropy(files)
        assert abs(result - 1.0) < 1e-9

    def test_skewed_distribution(self):
        # 3 from a.py, 1 from b.py → entropy < max
        files = ["a.py", "a.py", "a.py", "b.py"]
        result = file_entropy(files)
        assert 0.0 < result < 1.0

    def test_empty(self):
        assert file_entropy([]) == 0.0

    def test_two_files_equal(self):
        files = ["a.py", "b.py"]
        result = file_entropy(files)
        assert abs(result - 1.0) < 1e-9


# ===========================================================================
# M4 — Content Overlap
# ===========================================================================


class TestContentOverlap:
    def test_identical_blocks(self):
        blocks = ["def foo(): return bar", "def foo(): return bar"]
        result = content_overlap(blocks)
        assert abs(result - 1.0) < 1e-9

    def test_no_overlap(self):
        blocks = ["alpha bravo charlie", "delta echo foxtrot"]
        result = content_overlap(blocks)
        assert result == 0.0

    def test_partial_overlap(self):
        blocks = ["alpha bravo charlie", "charlie delta echo"]
        result = content_overlap(blocks)
        assert 0.0 < result < 1.0

    def test_single_block(self):
        assert content_overlap(["anything"]) == 0.0

    def test_empty(self):
        assert content_overlap([]) == 0.0

    def test_three_blocks_mean(self):
        # 3 blocks → 3 pairs
        blocks = [
            "alpha bravo charlie",
            "charlie delta echo",
            "echo foxtrot golf",
        ]
        result = content_overlap(blocks)
        assert 0.0 < result < 1.0


# ===========================================================================
# M5 — Score Separation
# ===========================================================================


class TestScoreSeparation:
    def test_all_same(self):
        # All scores identical → σ = 0 → CV = 0
        assert score_separation([5.0, 5.0, 5.0]) == 0.0

    def test_known_cv(self):
        # scores = [2, 4, 6] → μ = 4, σ² = (4+0+4)/3 = 8/3, σ = sqrt(8/3)
        scores = [2.0, 4.0, 6.0]
        mu = 4.0
        sigma = math.sqrt(8.0 / 3.0)
        expected_cv = sigma / mu
        result = score_separation(scores)
        assert abs(result - expected_cv) < 1e-9

    def test_empty(self):
        assert score_separation([]) == 0.0

    def test_mean_near_zero(self):
        scores = [0.0, 0.0, 0.0]
        assert score_separation(scores) == 0.0


# ===========================================================================
# M6 — Reranker Influence
# ===========================================================================


class TestRerankerInfluence:
    def test_reranker_dominates(self):
        # final = rerank (no base contribution)
        final = [1.0, 2.0, 3.0]
        rerank = [1.0, 2.0, 3.0]
        w_rerank = 1.0
        result = reranker_influence(final, rerank, w_rerank)
        assert abs(result - 1.0) < 1e-9

    def test_no_variance(self):
        final = [5.0, 5.0, 5.0]
        rerank = [1.0, 2.0, 3.0]
        result = reranker_influence(final, rerank, 1.0)
        assert result == 0.0  # var(final) = 0

    def test_partial_influence(self):
        final = [1.0, 3.0, 5.0]
        rerank = [0.5, 1.0, 1.5]
        result = reranker_influence(final, rerank, 0.5)
        assert 0.0 < result < 1.0

    def test_empty(self):
        assert reranker_influence([], [], 1.0) == 0.0

    def test_mismatched_lengths(self):
        assert reranker_influence([1.0, 2.0], [1.0], 1.0) == 0.0


# ===========================================================================
# M7 — Budget Utilization
# ===========================================================================


class TestBudgetUtilization:
    def test_full(self):
        assert budget_utilization(4000, 4000) == 1.0

    def test_half(self):
        assert budget_utilization(2000, 4000) == 0.5

    def test_empty(self):
        assert budget_utilization(0, 4000) == 0.0

    def test_over_budget(self):
        result = budget_utilization(5000, 4000)
        assert result > 1.0

    def test_zero_budget(self):
        assert budget_utilization(100, 0) == 0.0


# ===========================================================================
# PercentileWindow
# ===========================================================================


class TestPercentileWindow:
    def test_cold_start(self):
        w = PercentileWindow(max_size=100)
        assert w.percentile(5.0) == 0.5

    def test_basic_percentile(self):
        w = PercentileWindow(max_size=100)
        for i in range(100):
            w.add(float(i))
        # Value 50 should be at ~50th percentile
        p = w.percentile(50.0)
        assert 0.45 < p < 0.55

    def test_min_value(self):
        w = PercentileWindow(max_size=100)
        for i in range(1, 101):
            w.add(float(i))
        p = w.percentile(0.0)
        assert p == 0.0

    def test_max_value(self):
        w = PercentileWindow(max_size=100)
        for i in range(100):
            w.add(float(i))
        p = w.percentile(999.0)
        assert p == 1.0

    def test_eviction(self):
        w = PercentileWindow(max_size=5)
        for i in range(10):
            w.add(float(i))
        assert w.count == 5

    def test_is_reliable(self):
        w = PercentileWindow(max_size=100)
        assert not w.is_reliable
        for i in range(30):
            w.add(float(i))
        assert w.is_reliable

    def test_serialization(self):
        w = PercentileWindow(max_size=50)
        for i in range(10):
            w.add(float(i))
        data = w.to_dict()
        w2 = PercentileWindow.from_dict(data)
        assert w2.count == 10
        assert w2.max_size == 50


# ===========================================================================
# PercentileTracker
# ===========================================================================


class TestPercentileTracker:
    def test_default_keys(self):
        t = PercentileTracker(max_size=100)
        assert "semantic_strength" in t.windows
        assert "score_separation" in t.windows

    def test_add_and_query(self):
        t = PercentileTracker(max_size=100)
        for i in range(100):
            t.add("semantic_strength", float(i) / 100)
        p = t.percentile("semantic_strength", 0.5)
        assert 0.45 < p < 0.55

    def test_unknown_metric(self):
        t = PercentileTracker(max_size=100)
        p = t.percentile("unknown_metric", 1.0)
        assert p == 0.5  # No history

    def test_persistence(self, tmp_path):
        path = tmp_path / "tracker.json"
        t = PercentileTracker(max_size=100)
        for i in range(50):
            t.add("semantic_strength", float(i))
        t.save(path)

        t2 = PercentileTracker.load(path, max_size=100)
        assert t2.windows["semantic_strength"].count == 50


# ===========================================================================
# MetricRecord
# ===========================================================================


class TestMetricRecord:
    def test_frozen(self):
        r = MetricRecord(
            query_id="q1", run_id="r1", timestamp_utc="2026-01-01T00:00:00Z",
            score_separation=0.5, reranker_influence=0.3,
            semantic_strength=0.7, query_term_recall=0.8,
            file_entropy=0.6, content_overlap=0.1, budget_utilization=0.9,
            block_count=10, unique_file_count=5, candidate_count=40,
            reranker_available=True,
        )
        with pytest.raises(AttributeError):
            r.semantic_strength = 0.99  # type: ignore

    def test_roundtrip_json(self):
        r = MetricRecord(
            query_id="q1", run_id="r1", timestamp_utc="2026-01-01T00:00:00Z",
            score_separation=0.5, reranker_influence=0.3,
            semantic_strength=0.7, query_term_recall=0.8,
            file_entropy=0.6, content_overlap=0.1, budget_utilization=0.9,
            block_count=10, unique_file_count=5, candidate_count=40,
            reranker_available=True,
        )
        j = r.to_json()
        data = json.loads(j)
        r2 = MetricRecord(**data)
        assert r2.semantic_strength == 0.7
        assert r2.query_id == "q1"


# ===========================================================================
# MetricStorage
# ===========================================================================


class TestMetricStorage:
    def test_append_and_read(self, tmp_path):
        path = tmp_path / "metrics.jsonl"
        storage = MetricStorage(path)

        record = MetricRecord(
            query_id="q1", run_id="r1", timestamp_utc="2026-01-01T00:00:00Z",
            score_separation=0.5, reranker_influence=0.3,
            semantic_strength=0.7, query_term_recall=0.8,
            file_entropy=0.6, content_overlap=0.1, budget_utilization=0.9,
            block_count=10, unique_file_count=5, candidate_count=40,
            reranker_available=True,
        )
        storage.append(record)
        storage.append(record)

        records = storage.read_all()
        assert len(records) == 2
        assert records[0].query_id == "q1"

    def test_read_missing_file(self, tmp_path):
        path = tmp_path / "nonexistent.jsonl"
        storage = MetricStorage(path)
        assert storage.read_all() == []


# ===========================================================================
# Full Kernel Integration (with mock pipeline objects)
# ===========================================================================


@dataclass(frozen=True)
class MockContextBlock:
    block_id: str
    file: str
    start_line: int = 0
    end_line: int = 0
    content: str = ""
    symbol_id: str | None = None
    symbol_name: str | None = None
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True)
class MockContextArtifact:
    query_id: str
    context_text: str
    blocks: tuple
    token_budget: int
    used_tokens: int
    provenance: dict
    explain_trace: tuple[str, ...] = ()


@dataclass(frozen=True)
class MockFeatureVector:
    bm25_percentile: float = 0.5
    dense_percentile: float = 0.5
    name_match_score: float = 0.0
    is_entrypoint: bool = False
    has_decorator: bool = False
    callgraph_distance: float = 0.0


@dataclass(frozen=True)
class MockDebugTrace:
    candidate_id: str
    base_score: float
    rerank_score: float
    struct_bonus: float = 0.0
    final_score: float = 0.0
    features: MockFeatureVector | None = None
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True)
class MockRankMetadata:
    latency_ms: int = 100
    reranker_used: bool = True
    reranker_unavailable: bool = False
    candidate_count: int = 40
    set_optimization: dict | None = None
    signal_profile: dict | None = None
    ranking_concentration: dict | None = None
    ranking_geometry: dict | None = None


@dataclass(frozen=True)
class MockRankingOutput:
    ranked_candidates: tuple = ()
    debug_traces: tuple = ()
    metadata: MockRankMetadata = MockRankMetadata()


@dataclass
class MockRankConfig:
    reranker_enabled: bool = True
    reranker_model: str = "test"
    reranker_top_m: int = 20
    w_base: float = 0.3
    w_rerank: float = 0.5
    w_struct: float = 0.1
    w_bm25: float = 0.3
    w_dense: float = 0.7
    w_name: float = 0.1


class TestKernelIntegration:
    def _make_scenario(self):
        """Build a realistic mock scenario."""
        blocks = tuple(
            MockContextBlock(
                block_id=f"block_{i}",
                file=f"src/module_{i % 3}.py",
                content=f"def function_{i}(): return {i} + value_{i}",
            )
            for i in range(6)
        )

        traces = tuple(
            MockDebugTrace(
                candidate_id=f"block_{i}",
                base_score=0.3 + i * 0.05,
                rerank_score=0.5 + i * 0.08,
                final_score=0.4 + i * 0.06,
            )
            for i in range(10)  # More candidates than selected blocks
        )

        context = MockContextArtifact(
            query_id="test_q1",
            context_text="combined content",
            blocks=blocks,
            token_budget=4000,
            used_tokens=3200,
            provenance={"query": "how does function_3 work with module_1"},
        )

        ranking = MockRankingOutput(
            debug_traces=traces,
            metadata=MockRankMetadata(candidate_count=10),
        )

        config = MockRankConfig()

        return context, ranking, config

    def test_full_evaluation(self):
        from homllm.quality.kernel import ContextQualityKernel

        context, ranking, config = self._make_scenario()

        kernel = ContextQualityKernel()
        record = kernel.evaluate(
            ranking_output=ranking,
            rank_config=config,
            context_artifact=context,
            run_id="test_run_001",
        )

        # All metrics should be non-negative
        assert record.semantic_strength >= 0.0
        assert record.query_term_recall >= 0.0
        assert record.file_entropy >= 0.0
        assert record.content_overlap >= 0.0
        assert record.score_separation >= 0.0
        assert record.reranker_influence >= 0.0
        assert record.budget_utilization >= 0.0

        # Budget utilization should be 3200/4000 = 0.8
        assert abs(record.budget_utilization - 0.8) < 1e-6

        # File entropy should be > 0 (3 unique files from 6 blocks)
        assert record.file_entropy > 0.0

        # Block count should be 6
        assert record.block_count == 6
        assert record.unique_file_count == 3
        assert record.candidate_count == 10

    def test_with_tracker_and_storage(self, tmp_path):
        from homllm.quality.kernel import ContextQualityKernel

        context, ranking, config = self._make_scenario()

        tracker = PercentileTracker(max_size=100)
        storage = MetricStorage(tmp_path / "metrics.jsonl")

        kernel = ContextQualityKernel(tracker=tracker, storage=storage)
        record = kernel.evaluate(
            ranking_output=ranking,
            rank_config=config,
            context_artifact=context,
            run_id="test_run_002",
        )

        # Tracker should have 1 value per metric
        assert tracker.windows["semantic_strength"].count == 1

        # Storage should have 1 record
        records = storage.read_all()
        assert len(records) == 1
        assert records[0].query_id == "test_q1"

    def test_percentiles(self):
        from homllm.quality.kernel import ContextQualityKernel

        context, ranking, config = self._make_scenario()

        tracker = PercentileTracker(max_size=100)
        kernel = ContextQualityKernel(tracker=tracker)

        # Run 50 evaluations to build window
        for i in range(50):
            kernel.evaluate(
                ranking_output=ranking,
                rank_config=config,
                context_artifact=context,
                run_id=f"run_{i}",
            )

        # Now compute percentiles
        record = kernel.evaluate(
            ranking_output=ranking,
            rank_config=config,
            context_artifact=context,
            run_id="run_final",
        )

        percentiles = kernel.percentiles(record)
        assert "semantic_strength" in percentiles
        assert "score_separation" in percentiles
        # All percentiles should be valid (0-1)
        for name, p in percentiles.items():
            assert 0.0 <= p <= 1.0, f"{name} percentile out of range: {p}"

    def test_ranking_metrics_standalone(self):
        from homllm.quality.kernel import ContextQualityKernel

        _, ranking, config = self._make_scenario()
        kernel = ContextQualityKernel()

        result = kernel.compute_ranking_metrics(ranking, config)
        assert result.score_separation >= 0.0
        assert result.reranker_influence >= 0.0
        assert result.candidate_count == 10
        assert result.reranker_available is True
