import sys
from dataclasses import dataclass
from types import ModuleType

import pytest

from homllm.agent.orchestrator import (
    AgenticIterationSnapshot,
    ReadOnlyPlannerDecision,
    agentic_pass_signature,
    apply_read_only_iteration_retrieval_config,
    build_read_only_planner_prompt,
    default_followup_overrides,
    invoke_read_only_planner,
    normalize_planner_action,
    sanitize_planner_overrides,
)


@dataclass(frozen=True)
class DummyRetrievalConfig:
    bm25_top_k: int = 10
    vector_top_k: int = 20
    post_merge_candidates: int = 30
    precision_recovery_scan_candidates: int = 4
    precision_recovery_max_additions: int = 2
    coverage_recovery_max_additions: int = 3
    precision_recovery_min_confidence: float = 0.8


class DummyRetrievalResult:
    def __init__(self, count: int):
        self.candidates = [object() for _ in range(count)]


class DummyRankingOutput:
    def __init__(self, count: int):
        self.ranked_candidates = [object() for _ in range(count)]


class DummyContextArtifact:
    def __init__(self, blocks: int, used_tokens: int):
        self.blocks = [object() for _ in range(blocks)]
        self.used_tokens = used_tokens


class DummyPlannerResponse:
    def __init__(self, text: str):
        self.text = text


class DummyPlannerProvider:
    def __init__(self, text: str):
        self.text = text

    def invoke_sync(self, request):
        return DummyPlannerResponse(self.text)


class FailingPlannerProvider:
    def invoke_sync(self, request):
        raise RuntimeError("planner unavailable")


@dataclass
class DummyModelConfig:
    temperature: float
    max_output_tokens: int


@dataclass
class DummyProviderRequest:
    prompt: str
    model: str
    config: DummyModelConfig
    stream: bool = False


class DummyJSONParser:
    parsed_by_text = {}

    def parse(self, text: str):
        if text in self.parsed_by_text:
            return self.parsed_by_text[text], []
        return None, []


@pytest.fixture(autouse=True)
def stub_generation_contracts(monkeypatch):
    generation_module = ModuleType("homllm.generation")
    interfaces_module = ModuleType("homllm.generation.interfaces")
    parser_module = ModuleType("homllm.generation.parser")
    interfaces_module.ModelConfig = DummyModelConfig
    interfaces_module.ProviderRequest = DummyProviderRequest
    parser_module.ResilientJSONParser = DummyJSONParser
    DummyJSONParser.parsed_by_text = {}

    monkeypatch.setitem(sys.modules, "homllm.generation", generation_module)
    monkeypatch.setitem(sys.modules, "homllm.generation.interfaces", interfaces_module)
    monkeypatch.setitem(sys.modules, "homllm.generation.parser", parser_module)


def make_snapshot() -> AgenticIterationSnapshot:
    return AgenticIterationSnapshot(
        iteration=1,
        retrieval_overrides={},
        retrieval_candidates=50,
        ranking_candidates=42,
        context_blocks=36,
        context_tokens=3612,
        context_budget=5200,
        insufficiency_detected=False,
        planner_action="",
        planner_reason="",
        planner_parse_ok=True,
        planner_raw_text="",
        repeated_signature_count=1,
        signature="ret=50|rank=42|blocks=36|tok_bucket=36",
    )


def test_read_only_planner_decision_defaults_to_answer():
    decision = ReadOnlyPlannerDecision.answer("single_pass_mode")

    assert decision.action == "answer"
    assert decision.reason == "single_pass_mode"
    assert decision.overrides == {}
    assert decision.parse_ok is True
    assert decision.raw_text == ""


def test_normalize_planner_action_maps_retrieval_aliases():
    assert normalize_planner_action("retrieve") == "retrieve_context"
    assert normalize_planner_action("search") == "retrieve_context"
    assert normalize_planner_action("continue") == "retrieve_context"
    assert normalize_planner_action("answer") == "answer"
    assert normalize_planner_action("nonsense") == "answer"


def test_sanitize_planner_overrides_clamps_known_numeric_values():
    sanitized = sanitize_planner_overrides(
        {
            "bm25_top_k": "999",
            "vector_top_k": 0,
            "post_merge_candidates": 900,
            "precision_recovery_scan_candidates": "12",
            "precision_recovery_max_additions": -4,
            "coverage_recovery_max_additions": 99,
            "precision_recovery_min_confidence": "0.12345",
            "unknown": 123,
        }
    )

    assert sanitized == {
        "bm25_top_k": 500,
        "vector_top_k": 1,
        "post_merge_candidates": 800,
        "precision_recovery_scan_candidates": 12,
        "precision_recovery_max_additions": 0,
        "coverage_recovery_max_additions": 32,
        "precision_recovery_min_confidence": 0.123,
    }


def test_default_followup_overrides_broadens_without_exceeding_confidence_floor():
    overrides = default_followup_overrides(DummyRetrievalConfig(), iteration=2)

    assert overrides["bm25_top_k"] == 14
    assert overrides["vector_top_k"] == 28
    assert overrides["post_merge_candidates"] == 50
    assert overrides["precision_recovery_scan_candidates"] == 8
    assert overrides["coverage_recovery_max_additions"] == 5
    assert overrides["precision_recovery_min_confidence"] == 0.7


def test_apply_read_only_iteration_retrieval_config_returns_replaced_config():
    base = DummyRetrievalConfig()
    updated, overrides = apply_read_only_iteration_retrieval_config(
        base,
        {"bm25_top_k": 40, "unknown": 1},
    )

    assert updated is not base
    assert updated.bm25_top_k == 40
    assert updated.vector_top_k == 20
    assert overrides == {"bm25_top_k": 40}


def test_agentic_pass_signature_buckets_context_tokens():
    signature = agentic_pass_signature(
        DummyRetrievalResult(50),
        DummyRankingOutput(42),
        DummyContextArtifact(blocks=36, used_tokens=3612),
    )

    assert signature == "ret=50|rank=42|blocks=36|tok_bucket=36"


def test_build_read_only_planner_prompt_contains_strict_json_contract():
    snapshot = make_snapshot()

    prompt = build_read_only_planner_prompt(
        query="Trace the execution flow through all layers",
        iteration=1,
        max_iterations=3,
        last_snapshot=snapshot,
    )

    assert "Return ONLY strict JSON" in prompt
    assert '"action": "retrieve_context" | "answer"' in prompt
    assert "Trace the execution flow through all layers" in prompt
    assert '"remaining_iterations": 2' in prompt


def test_invoke_read_only_planner_uses_partial_action_from_malformed_output():
    decision = invoke_read_only_planner(
        provider=DummyPlannerProvider('{"action": "retrieve_context"'),
        model_name="dummy",
        query="Need more context",
        iteration=1,
        max_iterations=3,
        last_snapshot=make_snapshot(),
    )

    assert decision.action == "retrieve_context"
    assert decision.reason == "planner_partial_parse_action_only"
    assert decision.overrides == {}
    assert decision.parse_ok is False


def test_invoke_read_only_planner_forces_partial_action_to_answer_at_max():
    decision = invoke_read_only_planner(
        provider=DummyPlannerProvider('{"action": "retrieve_context"'),
        model_name="dummy",
        query="Need more context",
        iteration=3,
        max_iterations=3,
        last_snapshot=make_snapshot(),
    )

    assert decision.action == "answer"
    assert decision.reason == "planner_partial_parse_action_only"
    assert decision.overrides == {}
    assert decision.parse_ok is False


def test_invoke_read_only_planner_defaults_malformed_output_to_retrieve_before_max():
    decision = invoke_read_only_planner(
        provider=DummyPlannerProvider("not json at all"),
        model_name="dummy",
        query="Need more context",
        iteration=1,
        max_iterations=3,
        last_snapshot=make_snapshot(),
    )

    assert decision.action == "retrieve_context"
    assert decision.reason == "planner_parse_failed_default_retrieve_context"
    assert decision.overrides == {}
    assert decision.parse_ok is False


def test_invoke_read_only_planner_defaults_malformed_output_to_answer_at_max():
    decision = invoke_read_only_planner(
        provider=DummyPlannerProvider("not json at all"),
        model_name="dummy",
        query="Need more context",
        iteration=3,
        max_iterations=3,
        last_snapshot=make_snapshot(),
    )

    assert decision.action == "answer"
    assert decision.reason == "planner_parse_failed_default_answer"
    assert decision.overrides == {}
    assert decision.parse_ok is False


def test_invoke_read_only_planner_provider_exception_returns_answer():
    decision = invoke_read_only_planner(
        provider=FailingPlannerProvider(),
        model_name="dummy",
        query="Need more context",
        iteration=1,
        max_iterations=3,
        last_snapshot=make_snapshot(),
    )

    assert decision.action == "answer"
    assert decision.reason.startswith("planner_error:")
    assert decision.overrides == {}
    assert decision.parse_ok is False


def test_invoke_read_only_planner_valid_retrieve_preserves_reason_and_sanitizes_overrides():
    DummyJSONParser.parsed_by_text["valid retrieve"] = {
        "action": "retrieve_context",
        "reason": "need broader evidence",
        "overrides": {
            "bm25_top_k": "999",
            "vector_top_k": 0,
            "unknown": 123,
        },
    }

    decision = invoke_read_only_planner(
        provider=DummyPlannerProvider("valid retrieve"),
        model_name="dummy",
        query="Need more context",
        iteration=1,
        max_iterations=3,
        last_snapshot=make_snapshot(),
    )

    assert decision.action == "retrieve_context"
    assert decision.reason == "need broader evidence"
    assert decision.overrides == {"bm25_top_k": 500, "vector_top_k": 1}
    assert decision.parse_ok is True


def test_invoke_read_only_planner_valid_answer_drops_overrides():
    DummyJSONParser.parsed_by_text["valid answer"] = {
        "action": "answer",
        "reason": "context is enough",
        "overrides": {"bm25_top_k": 250},
    }

    decision = invoke_read_only_planner(
        provider=DummyPlannerProvider("valid answer"),
        model_name="dummy",
        query="Need more context",
        iteration=1,
        max_iterations=3,
        last_snapshot=make_snapshot(),
    )

    assert decision.action == "answer"
    assert decision.reason == "context is enough"
    assert decision.overrides == {}
    assert decision.parse_ok is True


def test_invoke_read_only_planner_valid_retrieve_forced_to_answer_at_max():
    DummyJSONParser.parsed_by_text["valid retrieve at max"] = {
        "action": "retrieve_context",
        "reason": "need broader evidence",
        "overrides": {"bm25_top_k": 250},
    }

    decision = invoke_read_only_planner(
        provider=DummyPlannerProvider("valid retrieve at max"),
        model_name="dummy",
        query="Need more context",
        iteration=3,
        max_iterations=3,
        last_snapshot=make_snapshot(),
    )

    assert decision.action == "answer"
    assert decision.reason == "need broader evidence"
    assert decision.overrides == {}
    assert decision.parse_ok is True
