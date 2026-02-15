"""Determinism tests for Retrieval layer."""

import math
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from homllm.common.types import Intent
from homllm.retrieval.interfaces import Candidate, PreparedQuery, RetrievalConfig
from homllm.retrieval.pipeline import RetrievalPipeline


class _FakePreparer:
    """Deterministic query preparer for retrieval determinism tests."""

    def prepare(self, query: str, intent: Intent) -> PreparedQuery:
        return PreparedQuery(
            dense_query=query,
            lexical_terms=[tok for tok in query.lower().split() if tok],
            intent=intent,
        )


class _FakeGraphStitch:
    """Deterministic graph stitch stub used to exercise graph path."""

    def expand(self, candidates: list[Candidate], query: str) -> list[Candidate]:
        if any(c.doc_id == "graph_stitch:deterministic" for c in candidates):
            return candidates
        return [
            *candidates,
            Candidate(
                doc_id="graph_stitch:deterministic",
                file="pkg/graph.py",
                symbol_id="graph_det",
                content="def graph_det(): pass",
                provenance=("graph_stitch:calls:hop1",),
            ),
        ]


class _FakeBM25Retriever:
    def __init__(self, results: list[Candidate], *, thread_safe: bool):
        self._results = list(results)
        self._thread_safe = thread_safe
        self.clone_calls = 0

    def search(self, query: str, top_k: int) -> list[Candidate]:
        return list(self._results[:top_k])

    def supports_thread_safe_search(self) -> bool:
        return self._thread_safe

    def clone_for_search(self):
        self.clone_calls += 1
        return _FakeBM25Retriever(list(self._results), thread_safe=self._thread_safe)


class _FakeVectorRetriever:
    def __init__(self, results: list[Candidate], *, thread_safe: bool):
        self._results = list(results)
        self._thread_safe = thread_safe
        self.clone_calls = 0

    def search(self, query: str, top_k: int) -> list[Candidate]:
        return list(self._results[:top_k])

    def supports_thread_safe_search(self) -> bool:
        return self._thread_safe

    def clone_for_search(self):
        self.clone_calls += 1
        return _FakeVectorRetriever(list(self._results), thread_safe=self._thread_safe)


class _RecordingRetriever:
    def __init__(self, results: list[Candidate]):
        self.results = list(results)
        self.calls: list[int] = []

    def search(self, query: str, top_k: int) -> list[Candidate]:
        self.calls.append(top_k)
        return list(self.results[:top_k])

    def supports_thread_safe_search(self) -> bool:
        return True

    def clone_for_search(self):
        clone = _RecordingRetriever(self.results)
        clone.calls = self.calls
        return clone


def _build_test_config(
    plan_b_enabled: bool,
    graph_stitch_enabled: bool,
    *,
    parallel_search_enabled: bool = False,
    static_ceiling_experiment_enabled: bool = False,
    static_ceiling_branch_multiplier: int = 1,
    static_ceiling_post_merge_multiplier: int = 1,
    static_ceiling_output_multiplier: int = 1,
) -> RetrievalConfig:
    return RetrievalConfig(
        bm25_top_k=50,
        vector_top_k=50,
        hybrid_method="rrf",
        rrf_k=10,
        bm25_weight=0.5,
        vector_weight=0.5,
        parallel_search_enabled=parallel_search_enabled,
        static_ceiling_experiment_enabled=static_ceiling_experiment_enabled,
        static_ceiling_branch_multiplier=static_ceiling_branch_multiplier,
        static_ceiling_post_merge_multiplier=static_ceiling_post_merge_multiplier,
        static_ceiling_output_multiplier=static_ceiling_output_multiplier,
        expansion_enabled=True,
        expansion_max_additions=4,
        expansion_min_similarity=0.25,
        plan_b_enabled=plan_b_enabled,
        diversity_mmr_enabled=False,
        granularity_boost_enabled=False,
        graph_stitch_enabled=graph_stitch_enabled,
        budget_aware_selection=False,
        granularity_mixing_enabled=False,
        hierarchical_dedup_enabled=False,
        post_merge_candidates=0,
    )


def _deterministic_bm25_results() -> list[Candidate]:
    return [
        Candidate(
            doc_id="doc_a",
            file="pkg/a.py",
            symbol_id="sym_a",
            content="def a(): return 1",
            bm25_score=12.0,
            provenance=("bm25",),
        ),
        Candidate(
            doc_id="doc_b",
            file="pkg/b.py",
            symbol_id="sym_b",
            content="def b(): return 2",
            bm25_score=10.0,
            provenance=("bm25",),
        ),
        Candidate(
            doc_id="doc_c",
            file="pkg/c.py",
            symbol_id="sym_c",
            content="def c(): return 3",
            bm25_score=8.0,
            provenance=("bm25",),
        ),
    ]


def _deterministic_vector_results() -> list[Candidate]:
    return [
        Candidate(
            doc_id="doc_b",
            file="pkg/b.py",
            symbol_id="sym_b",
            content="def b(): return 2",
            vector_score=0.95,
            provenance=("vector",),
        ),
        Candidate(
            doc_id="doc_d",
            file="pkg/d.py",
            symbol_id="sym_d",
            content="def d(): return 4",
            vector_score=0.90,
            provenance=("vector",),
        ),
        Candidate(
            doc_id="doc_a",
            file="pkg/a.py",
            symbol_id="sym_a",
            content="def a(): return 1",
            vector_score=0.80,
            provenance=("vector",),
        ),
    ]


def _assert_no_duplicate_doc_ids(candidates: list[Candidate]) -> None:
    doc_ids = [c.doc_id for c in candidates]
    assert len(doc_ids) == len(set(doc_ids))


def _assert_equal_candidate_surfaces(
    run_one: list[Candidate],
    run_two: list[Candidate],
    epsilon: float = 1e-12,
) -> None:
    assert len(run_one) == len(run_two)
    _assert_no_duplicate_doc_ids(run_one)
    _assert_no_duplicate_doc_ids(run_two)

    one_ids = [c.doc_id for c in run_one]
    two_ids = [c.doc_id for c in run_two]
    assert one_ids == two_ids

    one_provenance = [c.provenance for c in run_one]
    two_provenance = [c.provenance for c in run_two]
    assert one_provenance == two_provenance

    one_scores = [c.hybrid_score for c in run_one]
    two_scores = [c.hybrid_score for c in run_two]
    for lhs, rhs in zip(one_scores, two_scores):
        assert math.isclose(lhs, rhs, rel_tol=epsilon, abs_tol=epsilon)


@pytest.mark.parametrize(
    ("plan_b_enabled", "graph_stitch_enabled"),
    [
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    ],
)
def test_retrieval_determinism_matrix(
    plan_b_enabled: bool,
    graph_stitch_enabled: bool,
):
    """
    Same query + same index/config must produce deterministic retrieval surface.

    Determinism assertions:
    - ordered doc_id equality
    - score equality within epsilon
    - provenance equality
    - candidate count equality
    - no duplicate doc_ids
    """
    config = _build_test_config(
        plan_b_enabled,
        graph_stitch_enabled,
        parallel_search_enabled=False,
    )

    with TemporaryDirectory() as tmpdir:
        bm25_path = Path(tmpdir) / "bm25.index"
        vector_path = Path(tmpdir) / "vectors.lance"

        pipeline = RetrievalPipeline(config, bm25_path, vector_path)
        pipeline.preparer = _FakePreparer()
        pipeline._detect_legacy_index = lambda: False  # type: ignore[method-assign]
        pipeline._load_callgraph = lambda: {}  # type: ignore[method-assign]
        pipeline.expander.expand = lambda candidates, query, callgraph, cfg: candidates  # type: ignore[method-assign]
        pipeline.precision_recovery.recover = (  # type: ignore[method-assign]
            lambda candidates, query, cfg, max_additions=3: candidates
        )
        pipeline.bm25_retriever.search = (  # type: ignore[method-assign]
            lambda query, top_k: _deterministic_bm25_results()[:top_k]
        )
        pipeline.vector_retriever.search = (  # type: ignore[method-assign]
            lambda query, top_k: _deterministic_vector_results()[:top_k]
        )

        if plan_b_enabled and graph_stitch_enabled:
            pipeline._graph_stitch_expander = _FakeGraphStitch()  # type: ignore[attr-defined]
        else:
            pipeline._graph_stitch_expander = None  # type: ignore[attr-defined]

        query = "find authentication function"
        result1 = pipeline.retrieve(query, Intent.SEARCH)
        result2 = pipeline.retrieve(query, Intent.SEARCH)

        _assert_equal_candidate_surfaces(result1.candidates, result2.candidates)

        graph_stitch_candidates = [
            c
            for c in result1.candidates
            if any(p.startswith("graph_stitch:") for p in c.provenance)
        ]
        if plan_b_enabled and graph_stitch_enabled:
            assert graph_stitch_candidates
        else:
            assert not graph_stitch_candidates


def test_parallel_and_sequential_candidate_id_equality():
    """Parallel and sequential search modes must preserve identical retrieval surface."""
    seq_config = _build_test_config(False, False, parallel_search_enabled=False)
    par_config = _build_test_config(False, False, parallel_search_enabled=True)

    with TemporaryDirectory() as tmpdir:
        bm25_path = Path(tmpdir) / "bm25.index"
        vector_path = Path(tmpdir) / "vectors.lance"

        seq_pipeline = RetrievalPipeline(seq_config, bm25_path, vector_path)
        par_pipeline = RetrievalPipeline(par_config, bm25_path, vector_path)

        for pipeline in (seq_pipeline, par_pipeline):
            pipeline.preparer = _FakePreparer()
            pipeline._detect_legacy_index = lambda: False  # type: ignore[method-assign]
            pipeline._load_callgraph = lambda: {}  # type: ignore[method-assign]
            pipeline.expander.expand = lambda candidates, query, callgraph, cfg: candidates  # type: ignore[method-assign]
            pipeline.precision_recovery.recover = (  # type: ignore[method-assign]
                lambda candidates, query, cfg, max_additions=3: candidates
            )
            pipeline._graph_stitch_expander = None  # type: ignore[attr-defined]

        bm25_results = _deterministic_bm25_results()
        vector_results = _deterministic_vector_results()
        seq_pipeline.bm25_retriever = _FakeBM25Retriever(bm25_results, thread_safe=True)  # type: ignore[assignment]
        seq_pipeline.vector_retriever = _FakeVectorRetriever(vector_results, thread_safe=True)  # type: ignore[assignment]
        par_pipeline.bm25_retriever = _FakeBM25Retriever(bm25_results, thread_safe=True)  # type: ignore[assignment]
        par_pipeline.vector_retriever = _FakeVectorRetriever(vector_results, thread_safe=True)  # type: ignore[assignment]

        query = "find authentication function"
        seq_result = seq_pipeline.retrieve(query, Intent.SEARCH)
        par_result = par_pipeline.retrieve(query, Intent.SEARCH)

        _assert_equal_candidate_surfaces(seq_result.candidates, par_result.candidates)
        assert seq_result.metadata.get("search_mode") == "sequential"
        assert par_result.metadata.get("search_mode") == "parallel_shared"


def test_parallel_uses_branch_local_retrievers_when_not_thread_safe():
    """Parallel mode must fall back to branch-local retrievers when thread safety is unknown."""
    config = _build_test_config(False, False, parallel_search_enabled=True)

    with TemporaryDirectory() as tmpdir:
        bm25_path = Path(tmpdir) / "bm25.index"
        vector_path = Path(tmpdir) / "vectors.lance"
        pipeline = RetrievalPipeline(config, bm25_path, vector_path)
        pipeline.preparer = _FakePreparer()
        pipeline._detect_legacy_index = lambda: False  # type: ignore[method-assign]
        pipeline._load_callgraph = lambda: {}  # type: ignore[method-assign]
        pipeline.expander.expand = lambda candidates, query, callgraph, cfg: candidates  # type: ignore[method-assign]
        pipeline.precision_recovery.recover = (  # type: ignore[method-assign]
            lambda candidates, query, cfg, max_additions=3: candidates
        )
        pipeline._graph_stitch_expander = None  # type: ignore[attr-defined]

        bm25_stub = _FakeBM25Retriever(_deterministic_bm25_results(), thread_safe=False)
        vector_stub = _FakeVectorRetriever(_deterministic_vector_results(), thread_safe=False)
        pipeline.bm25_retriever = bm25_stub  # type: ignore[assignment]
        pipeline.vector_retriever = vector_stub  # type: ignore[assignment]

        result = pipeline.retrieve("find authentication function", Intent.SEARCH)
        assert result.candidates
        assert result.metadata.get("search_mode") == "parallel_branch_local"
        assert bm25_stub.clone_calls >= 1
        assert vector_stub.clone_calls >= 1


def test_static_ceiling_phase_a_applies_deterministic_multipliers():
    """Static ceiling Phase-A must deterministically scale retrieval limits."""
    config = _build_test_config(
        False,
        False,
        parallel_search_enabled=False,
        static_ceiling_experiment_enabled=True,
        static_ceiling_branch_multiplier=2,
        static_ceiling_post_merge_multiplier=2,
        static_ceiling_output_multiplier=2,
    )
    config.bm25_top_k = 3
    config.vector_top_k = 4
    config.post_merge_candidates = 5

    with TemporaryDirectory() as tmpdir:
        pipeline = RetrievalPipeline(config, Path(tmpdir) / "bm25.index", Path(tmpdir) / "vectors.lance")
        pipeline.preparer = _FakePreparer()
        pipeline._detect_legacy_index = lambda: False  # type: ignore[method-assign]
        pipeline._load_callgraph = lambda: {}  # type: ignore[method-assign]
        pipeline.expander.expand = lambda candidates, query, callgraph, cfg: candidates  # type: ignore[method-assign]
        pipeline.precision_recovery.recover = (  # type: ignore[method-assign]
            lambda candidates, query, cfg, max_additions=3: candidates
        )
        pipeline._graph_stitch_expander = None  # type: ignore[attr-defined]

        bm25_pool = [
            Candidate(
                doc_id=f"bm{i}",
                file="pkg/bm.py",
                symbol_id=f"sym_bm_{i}",
                content=f"def bm_{i}(): pass",
                bm25_score=100 - i,
                provenance=("bm25",),
            )
            for i in range(10)
        ]
        vector_pool = [
            Candidate(
                doc_id=f"vx{i}",
                file="pkg/vx.py",
                symbol_id=f"sym_vx_{i}",
                content=f"def vx_{i}(): pass",
                vector_score=1.0 - (i * 0.01),
                provenance=("vector",),
            )
            for i in range(10)
        ]

        bm_rec = _RecordingRetriever(bm25_pool)
        vx_rec = _RecordingRetriever(vector_pool)
        pipeline.bm25_retriever = bm_rec  # type: ignore[assignment]
        pipeline.vector_retriever = vx_rec  # type: ignore[assignment]

        result = pipeline.retrieve("find authentication function", Intent.SEARCH, top_k=5)
        assert result.metadata.get("static_ceiling_mode") == "static_ceiling_v1"
        assert result.metadata.get("effective_bm25_top_k") == 6
        assert result.metadata.get("effective_vector_top_k") == 8
        assert result.metadata.get("effective_post_merge_candidates") == 10
        assert result.metadata.get("effective_output_top_k") == 10
        assert bm_rec.calls == [6]
        assert vx_rec.calls == [8]
        assert len(result.candidates) <= 10
