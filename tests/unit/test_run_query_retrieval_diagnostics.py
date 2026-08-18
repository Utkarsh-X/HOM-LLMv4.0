import json
from pathlib import Path
from types import SimpleNamespace

from homllm.common.types import Intent
from runtime.run_query import (
    _should_apply_cqi_gate,
    _write_generation_diagnostics_artifact,
    _write_retrieval_diagnostics_artifact,
)


def test_write_retrieval_diagnostics_artifact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    retrieval_result = SimpleNamespace(
        metadata={
            "resolved_intent": "explain",
            "intent_source": "heuristic",
            "intent_rule": r"\\btrace\\b",
            "retrieval_stage_trace": {"bm25_raw": 10, "final_output": 5},
            "knee_gate": {"knee_position": 12, "post_knee_count": 20},
            "graph_stitch_status": "active",
            "graph_stitch_status_detail": {"loaded": True},
            "query_expansion_enabled": True,
            "query_expansion_terms": ["auth"],
            "effective_bm25_top_k": 50,
            "effective_vector_top_k": 50,
            "effective_post_merge_candidates": 50,
            "effective_output_top_k": 50,
            "adaptive_k": 65,
        },
        candidates=[
            SimpleNamespace(
                doc_id="d1",
                file="api/routes.py",
                symbol_id="s1",
                symbol_name="admin_search_endpoint",
                hybrid_score=1.25,
                provenance=("bm25",),
                granularity_level="fine",
            )
        ],
    )

    _write_retrieval_diagnostics_artifact(
        run_id="run123",
        query="Trace the execution flow",
        retrieval_result=retrieval_result,
        requested_intent=Intent.UNKNOWN,
        enabled=True,
    )

    out = Path("artifacts") / "runs" / "run123" / "retrieval_diagnostics.json"
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["resolved_intent"] == "explain"
    assert data["retrieval_stage_trace"]["final_output"] == 5
    assert data["granularity_counts_top20"]["fine"] == 1
    assert data["provenance_counts_top20"]["bm25"] == 1
    assert data["candidates_top20"][0]["symbol_name"] == "admin_search_endpoint"


def test_cqi_gate_disabled_when_reranker_disabled():
    ranking_config = SimpleNamespace(reranker_enabled=False)
    ranking_output = SimpleNamespace(metadata=SimpleNamespace(reranker_used=False, reranker_unavailable=False))
    cqi_result = {"cqi4": 0.10}

    assert _should_apply_cqi_gate(cqi_result, ranking_config, ranking_output) is False


def test_cqi_gate_disabled_when_reranker_not_used():
    ranking_config = SimpleNamespace(reranker_enabled=True)
    ranking_output = SimpleNamespace(metadata=SimpleNamespace(reranker_used=False, reranker_unavailable=False))
    cqi_result = {"cqi4": 0.10}

    assert _should_apply_cqi_gate(cqi_result, ranking_config, ranking_output) is False


def test_cqi_gate_enabled_only_when_low_cqi_and_reranker_active():
    ranking_config = SimpleNamespace(reranker_enabled=True)
    ranking_output = SimpleNamespace(metadata=SimpleNamespace(reranker_used=True, reranker_unavailable=False))

    assert _should_apply_cqi_gate({"cqi4": 0.10}, ranking_config, ranking_output) is True
    assert _should_apply_cqi_gate({"cqi4": 0.55}, ranking_config, ranking_output) is False


def test_write_generation_diagnostics_artifact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    generation_result = SimpleNamespace(
        status="OK",
        provider="GeminiProvider",
        model="gemini-3.5-flash-lite",
        tokens_in=123,
        tokens_out=456,
        latency_ms=789,
        finish_reason="stop",
        diagnostics=SimpleNamespace(
            parse_warnings=["warn1"],
            hallucination_flags=["citation_not_in_context: api/routes.py:999"],
            corrections_applied=["trimmed-json-fence"],
        ),
    )

    _write_generation_diagnostics_artifact("run456", generation_result)

    out = Path("artifacts") / "runs" / "run456" / "generation_diagnostics.json"
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["model"] == "gemini-3.5-flash-lite"
    assert data["hallucination_flags"] == ["citation_not_in_context: api/routes.py:999"]
    assert data["parse_warnings"] == ["warn1"]
