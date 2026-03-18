from homllm.context.interfaces import ContextConfig
from homllm.context.pipeline import ContextPipeline
from homllm.ranking.interfaces import DebugTrace, FeatureVector, RankMetadata, RankingOutput
from homllm.retrieval.interfaces import Candidate


def _make_candidate(doc_id: str, file: str, content: str, symbol_name: str | None = None) -> Candidate:
    return Candidate(
        doc_id=doc_id,
        file=file,
        symbol_id=doc_id,
        symbol_name=symbol_name or doc_id,
        content=content,
        provenance=("bm25",),
        span_start=1,
        span_end=max(1, len(content.splitlines())),
    )


def _make_trace(doc_id: str, score: float, name_match: float = 0.0) -> DebugTrace:
    return DebugTrace(
        candidate_id=doc_id,
        base_score=score,
        rerank_score=score,
        struct_bonus=0.0,
        final_score=score,
        features=FeatureVector(
            bm25_percentile=1.0,
            dense_percentile=1.0,
            name_match_score=name_match,
            is_entrypoint=False,
            has_decorator=False,
            callgraph_distance=0.0,
        ),
        provenance=("bm25",),
        rerank_evaluated=True,
    )


def test_low_value_suppression_drops_obvious_init_glue_when_safe():
    config = ContextConfig(
        max_tokens=2000,
        budget_mode="fixed",
        summarization_enabled=False,
        ordering="score_first",
        ranking_surface_lock_enabled=True,
        coherence_enabled=False,
        submodular_packer_enabled=False,
        generation_reserve_tokens=0,
        low_value_suppression_enabled=True,
        low_value_suppression_min_keep_blocks=2,
    )
    pipeline = ContextPipeline(config=config, tokenizer=None, callgraph={})

    candidates = (
        _make_candidate(
            "hdr",
            "pkg/__init__.py",
            '"""package docs"""\nfrom .core import run\n__all__ = ["run"]\n',
            "__init__",
        ),
        _make_candidate(
            "impl",
            "pkg/__init__.py",
            "def run():\n    value = 1\n    return value\n",
            "run",
        ),
        _make_candidate(
            "other",
            "pkg/worker.py",
            "def work():\n    return 2\n",
            "work",
        ),
    )
    traces = (
        _make_trace("hdr", 0.01),
        _make_trace("impl", 0.4),
        _make_trace("other", 0.3),
    )
    ranking_output = RankingOutput(
        ranked_candidates=candidates,
        debug_traces=traces,
        metadata=RankMetadata(latency_ms=1, reranker_used=True, reranker_unavailable=False, candidate_count=3),
    )

    artifact = pipeline.assemble(ranking_output=ranking_output, query="how does run work")

    suppression = artifact.provenance["low_value_suppression"]
    assert suppression["active"] is True
    assert suppression["blocks_suppressed"] == 1
    assert "hdr" in suppression["suppressed_block_ids"]
    drop_trace = {entry["block_id"]: entry for entry in artifact.provenance["context_drop_trace"]}
    assert drop_trace["hdr"]["drop_reason"] == "low_value_suppression"
    kept_ids = {block.block_id for block in artifact.blocks}
    assert "impl" in kept_ids
    assert "other" in kept_ids


def test_low_value_suppression_respects_min_keep_guard():
    config = ContextConfig(
        max_tokens=2000,
        budget_mode="fixed",
        summarization_enabled=False,
        ordering="score_first",
        ranking_surface_lock_enabled=True,
        coherence_enabled=False,
        submodular_packer_enabled=False,
        generation_reserve_tokens=0,
        low_value_suppression_enabled=True,
        low_value_suppression_min_keep_blocks=3,
    )
    pipeline = ContextPipeline(config=config, tokenizer=None, callgraph={})

    candidates = (
        _make_candidate(
            "hdr",
            "pkg/__init__.py",
            '"""package docs"""\nfrom .core import run\n__all__ = ["run"]\n',
            "__init__",
        ),
        _make_candidate(
            "impl",
            "pkg/__init__.py",
            "def run():\n    value = 1\n    return value\n",
            "run",
        ),
    )
    traces = (
        _make_trace("hdr", 0.01),
        _make_trace("impl", 0.4),
    )
    ranking_output = RankingOutput(
        ranked_candidates=candidates,
        debug_traces=traces,
        metadata=RankMetadata(latency_ms=1, reranker_used=True, reranker_unavailable=False, candidate_count=2),
    )

    artifact = pipeline.assemble(ranking_output=ranking_output, query="how does run work")

    suppression = artifact.provenance["low_value_suppression"]
    assert suppression["active"] is False
    assert suppression["reason"] in {"min_keep_guard", "no_eligible_low_value_blocks"}
    kept_ids = {block.block_id for block in artifact.blocks}
    assert "hdr" in kept_ids
    assert "impl" in kept_ids
