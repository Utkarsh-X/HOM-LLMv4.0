from homllm.common.types import Intent
from homllm.retrieval.intent_adapter import infer_retrieval_intent


def test_infer_retrieval_intent_explain_for_flow_question():
    result = infer_retrieval_intent("Trace the execution flow when admin_search_endpoint is called")
    assert result.intent == Intent.EXPLAIN


def test_infer_retrieval_intent_search_for_compare_question():
    result = infer_retrieval_intent("Compare LRU, LFU and TTL-only eviction")
    assert result.intent == Intent.SEARCH


def test_infer_retrieval_intent_debug_for_failure_question():
    result = infer_retrieval_intent("What causes NaN in cosine similarity?")
    assert result.intent == Intent.DEBUG


def test_infer_retrieval_intent_implement_for_should_question():
    result = infer_retrieval_intent("How should an embedding pipeline detect dimension mismatch?")
    assert result.intent == Intent.IMPLEMENT
