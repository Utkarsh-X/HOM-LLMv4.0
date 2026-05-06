from dataclasses import dataclass

from homllm.agent.contracts import AgenticMode, TaskClass
from homllm.agent.router import (
    RouteDecision,
    intent_to_task_class,
    resolve_agentic_mode,
    route_agentic_mode,
)
from homllm.common.types import Intent


@dataclass
class DummyAgenticConfig:
    enabled: bool = False
    default_mode: str = "single_pass"
    router_enabled: bool = False


def test_resolve_agentic_mode_accepts_supported_stage1_modes():
    assert resolve_agentic_mode("single_pass") == AgenticMode.SINGLE_PASS
    assert resolve_agentic_mode("read_only_agentic") == AgenticMode.READ_ONLY_AGENTIC


def test_resolve_agentic_mode_falls_back_to_single_pass_for_unknown_mode():
    assert resolve_agentic_mode("patch") == AgenticMode.SINGLE_PASS
    assert resolve_agentic_mode("not-a-mode") == AgenticMode.SINGLE_PASS
    assert resolve_agentic_mode("") == AgenticMode.SINGLE_PASS


def test_intent_to_task_class_maps_runtime_intents():
    assert intent_to_task_class(Intent.EXPLAIN) == TaskClass.EXPLAIN
    assert intent_to_task_class(Intent.IMPLEMENT) == TaskClass.IMPLEMENT
    assert intent_to_task_class(Intent.REFACTOR) == TaskClass.REFACTOR
    assert intent_to_task_class(Intent.DEBUG) == TaskClass.DEBUG
    assert intent_to_task_class(Intent.SEARCH) == TaskClass.SEARCH
    assert intent_to_task_class(Intent.UNKNOWN) == TaskClass.UNKNOWN


def test_disabled_agentic_always_routes_single_pass():
    decision = route_agentic_mode(
        DummyAgenticConfig(
            enabled=False,
            default_mode="read_only_agentic",
            router_enabled=True,
        ),
        intent=Intent.DEBUG,
        query="debug the cache failure across all layers",
    )

    assert decision == RouteDecision(
        mode=AgenticMode.SINGLE_PASS,
        task_class=TaskClass.DEBUG,
        reason="agentic_disabled",
    )


def test_router_disabled_preserves_default_mode_for_existing_canaries():
    decision = route_agentic_mode(
        DummyAgenticConfig(
            enabled=True,
            default_mode="read_only_agentic",
            router_enabled=False,
        ),
        intent=Intent.EXPLAIN,
        query="short explain query",
    )

    assert decision.mode == AgenticMode.READ_ONLY_AGENTIC
    assert decision.task_class == TaskClass.EXPLAIN
    assert decision.reason == "router_disabled_default_mode"


def test_router_enabled_keeps_simple_explain_and_search_single_pass():
    explain_decision = route_agentic_mode(
        DummyAgenticConfig(
            enabled=True,
            default_mode="read_only_agentic",
            router_enabled=True,
        ),
        intent=Intent.EXPLAIN,
        query="What does Config do?",
    )
    search_decision = route_agentic_mode(
        DummyAgenticConfig(
            enabled=True,
            default_mode="read_only_agentic",
            router_enabled=True,
        ),
        intent=Intent.SEARCH,
        query="Find RedisClient",
    )

    assert explain_decision.mode == AgenticMode.SINGLE_PASS
    assert explain_decision.reason == "simple_task_single_pass"
    assert search_decision.mode == AgenticMode.SINGLE_PASS
    assert search_decision.reason == "simple_task_single_pass"


def test_router_enabled_routes_complex_explain_and_action_tasks_read_only():
    complex_explain = route_agentic_mode(
        DummyAgenticConfig(
            enabled=True,
            default_mode="read_only_agentic",
            router_enabled=True,
        ),
        intent=Intent.EXPLAIN,
        query=(
            "Trace the execution flow through all layers including decorators, "
            "cache, optimizer, ranking, failures, and fallback behavior."
        ),
    )
    debug_decision = route_agentic_mode(
        DummyAgenticConfig(
            enabled=True,
            default_mode="read_only_agentic",
            router_enabled=True,
        ),
        intent=Intent.DEBUG,
        query="debug why ranking changes after context assembly",
    )

    assert complex_explain.mode == AgenticMode.READ_ONLY_AGENTIC
    assert complex_explain.reason == "complex_task_read_only_agentic"
    assert debug_decision.mode == AgenticMode.READ_ONLY_AGENTIC
    assert debug_decision.reason == "complex_task_read_only_agentic"
