from homllm.ranking.interfaces import RankConfig, RankingInput
from homllm.ranking.pipeline import RankingPipeline
from homllm.retrieval.interfaces import Candidate


def _rank_config(**overrides) -> RankConfig:
    base = RankConfig(
        reranker_enabled=False,
        reranker_model="unused",
        reranker_top_m=0,
        w_base=1.0,
        w_rerank=0.0,
        w_struct=0.0,
        w_bm25=0.4,
        w_dense=0.4,
        w_name=0.2,
        broad_system_bias_enabled=True,
        w_broad_system_positive=0.20,
        w_broad_system_negative=0.20,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_broad_system_bias_prefers_public_runtime_candidate():
    pipeline = RankingPipeline(config=_rank_config())
    query = "How does the system handle schema evolution across adapters when columns are missing and fallbacks exist?"
    adapter_candidate = Candidate(
        doc_id="a",
        file="database/adapters/postgres.py",
        symbol_id="db:PostgresAdapter_execute:1",
        symbol_name="PostgresAdapter_execute",
        content="execute query adapter path",
        bm25_score=1.0,
        vector_score=1.0,
        hybrid_score=1.0,
        doc_type="symbol",
    )
    helper_candidate = Candidate(
        doc_id="b",
        file="optimization/utils.py",
        symbol_id="opt:_estimate_cost:1",
        symbol_name="_estimate_cost",
        content="helper internals",
        bm25_score=1.0,
        vector_score=1.0,
        hybrid_score=1.0,
        doc_type="symbol",
    )

    output = pipeline.rank(
        RankingInput(query=query, candidates=(adapter_candidate, helper_candidate), config=_rank_config())
    )

    assert [c.doc_id for c in output.ranked_candidates][:2] == ["a", "b"]
    bias_summary = output.metadata.ranking_subtrace_summary["broad_system_bias"]
    assert bias_summary["enabled"] is True
    assert bias_summary["applied"] is True
    assert bias_summary["broad_system_bias_count"] >= 1


def test_broad_system_bias_has_no_effect_for_narrow_helper_question():
    pipeline = RankingPipeline(config=_rank_config())
    query = "Explain how _estimate_cost works internally."
    helper_candidate = Candidate(
        doc_id="b",
        file="optimization/utils.py",
        symbol_id="opt:_estimate_cost:1",
        symbol_name="_estimate_cost",
        content="helper internals",
        bm25_score=1.0,
        vector_score=1.0,
        hybrid_score=1.0,
        doc_type="symbol",
    )
    adapter_candidate = Candidate(
        doc_id="a",
        file="database/adapters/postgres.py",
        symbol_id="db:PostgresAdapter_execute:1",
        symbol_name="PostgresAdapter_execute",
        content="execute query adapter path",
        bm25_score=0.8,
        vector_score=0.8,
        hybrid_score=0.8,
        doc_type="symbol",
    )

    output = pipeline.rank(
        RankingInput(query=query, candidates=(adapter_candidate, helper_candidate), config=_rank_config())
    )

    assert output.ranked_candidates[0].doc_id == "b"
    bias_summary = output.metadata.ranking_subtrace_summary["broad_system_bias"]
    assert bias_summary["enabled"] is True
    assert bias_summary["applied"] is False
