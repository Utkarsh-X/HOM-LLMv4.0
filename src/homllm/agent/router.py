"""Routing policy for bounded agentic execution."""

from __future__ import annotations

from dataclasses import dataclass

from homllm.agent.contracts import AgenticMode, TaskClass
from homllm.common.types import Intent


@dataclass(frozen=True)
class RouteDecision:
    """Resolved execution mode for one runtime query."""

    mode: AgenticMode
    task_class: TaskClass
    reason: str


def intent_to_task_class(intent: Intent) -> TaskClass:
    """Map runtime retrieval intent to agentic task class."""
    mapping = {
        Intent.EXPLAIN: TaskClass.EXPLAIN,
        Intent.IMPLEMENT: TaskClass.IMPLEMENT,
        Intent.REFACTOR: TaskClass.REFACTOR,
        Intent.DEBUG: TaskClass.DEBUG,
        Intent.SEARCH: TaskClass.SEARCH,
        Intent.UNKNOWN: TaskClass.UNKNOWN,
    }
    return mapping.get(intent, TaskClass.UNKNOWN)


def resolve_agentic_mode(mode_name: str) -> AgenticMode:
    """Resolve Stage 1 supported modes, defaulting safely to single-pass."""
    normalized = str(mode_name or "").strip().lower()
    if normalized == AgenticMode.READ_ONLY_AGENTIC.value:
        return AgenticMode.READ_ONLY_AGENTIC
    if normalized == AgenticMode.SINGLE_PASS.value:
        return AgenticMode.SINGLE_PASS
    return AgenticMode.SINGLE_PASS


def _looks_complex(query: str) -> bool:
    """Heuristic for routing broad synthesis questions to read-only orchestration."""
    normalized = f" {str(query or '').strip().lower()} "
    words = normalized.split()
    complexity_markers = (
        " through all ",
        " all layers ",
        " including ",
        " trace ",
        " debug ",
        " failure ",
        " failures ",
        " fallback ",
        " fallbacks ",
        " lifecycle ",
        " end-to-end ",
        " interaction ",
        " interactions ",
        " combine ",
        " combines ",
    )
    return len(words) >= 18 or any(marker in normalized for marker in complexity_markers)


def route_agentic_mode(agentic_config, intent: Intent, query: str) -> RouteDecision:
    """Choose single-pass vs read-only agentic mode for the current query.

    When router_enabled is false, preserve configured default_mode so existing canary
    runs do not silently change behavior.
    """
    task_class = intent_to_task_class(intent)

    if not bool(getattr(agentic_config, "enabled", False)):
        return RouteDecision(
            mode=AgenticMode.SINGLE_PASS,
            task_class=task_class,
            reason="agentic_disabled",
        )

    configured_mode = resolve_agentic_mode(
        str(getattr(agentic_config, "default_mode", "single_pass"))
    )
    if not bool(getattr(agentic_config, "router_enabled", False)):
        return RouteDecision(
            mode=configured_mode,
            task_class=task_class,
            reason="router_disabled_default_mode",
        )

    if configured_mode != AgenticMode.READ_ONLY_AGENTIC:
        return RouteDecision(
            mode=AgenticMode.SINGLE_PASS,
            task_class=task_class,
            reason="configured_single_pass",
        )

    if task_class in {TaskClass.IMPLEMENT, TaskClass.REFACTOR, TaskClass.DEBUG}:
        return RouteDecision(
            mode=AgenticMode.READ_ONLY_AGENTIC,
            task_class=task_class,
            reason="complex_task_read_only_agentic",
        )

    if task_class == TaskClass.EXPLAIN and _looks_complex(query):
        return RouteDecision(
            mode=AgenticMode.READ_ONLY_AGENTIC,
            task_class=task_class,
            reason="complex_task_read_only_agentic",
        )

    return RouteDecision(
        mode=AgenticMode.SINGLE_PASS,
        task_class=task_class,
        reason="simple_task_single_pass",
    )
