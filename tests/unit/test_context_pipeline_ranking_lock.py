from homllm.context.interfaces import ContextConfig
from homllm.context.pipeline import ContextPipeline
from homllm.ranking.interfaces import DebugTrace, FeatureVector, RankMetadata, RankingOutput
from homllm.retrieval.interfaces import Candidate


def _make_candidate(doc_id: str, file: str) -> Candidate:
    return Candidate(
        doc_id=doc_id,
        file=file,
        symbol_id=doc_id,
        symbol_name=doc_id,
        content="def f():\n    return 1\n",
        provenance=("bm25",),
        span_start=1,
        span_end=2,
    )


def _make_trace(doc_id: str, score: float) -> DebugTrace:
    return DebugTrace(
        candidate_id=doc_id,
        base_score=score,
        rerank_score=score,
        struct_bonus=0.0,
        final_score=score,
        features=FeatureVector(
            bm25_percentile=1.0,
            dense_percentile=1.0,
            name_match_score=0.0,
            is_entrypoint=False,
            has_decorator=False,
            callgraph_distance=0.0,
        ),
        provenance=("bm25",),
        rerank_evaluated=True,
    )


def test_context_pipeline_falls_back_on_ranking_authority_violation(monkeypatch):
    config = ContextConfig(
        max_tokens=1000,
        budget_mode="fixed",
        summarization_enabled=False,
        ordering="score_first",
        ranking_surface_lock_enabled=True,
        coherence_enabled=False,
        submodular_packer_enabled=False,
        generation_reserve_tokens=0,
    )
    pipeline = ContextPipeline(config=config, tokenizer=None, callgraph={})

    candidates = (
        _make_candidate("a", "pkg/a.py"),
        _make_candidate("b", "pkg/b.py"),
        _make_candidate("c", "pkg/c.py"),
    )
    traces = (
        _make_trace("a", 3.0),
        _make_trace("b", 2.0),
        _make_trace("c", 1.0),
    )
    ranking_output = RankingOutput(
        ranked_candidates=candidates,
        debug_traces=traces,
        metadata=RankMetadata(
            latency_ms=1,
            reranker_used=True,
            reranker_unavailable=False,
            candidate_count=3,
        ),
    )

    reorder_counts = iter([1, 0])

    def fake_count_reorders(_ranking_ids, _allocated_ids):
        return next(reorder_counts)

    monkeypatch.setattr(pipeline, "_count_reorders", fake_count_reorders)

    artifact = pipeline.assemble(ranking_output=ranking_output, query="test query")

    fallback = artifact.provenance["ranking_authority_fallback"]
    assert fallback["active"] is True
    assert fallback["reason"] == "context_reorder_count_violation"
    assert artifact.provenance["ranking_order_preserved"] is True
    assert len(artifact.blocks) > 0
