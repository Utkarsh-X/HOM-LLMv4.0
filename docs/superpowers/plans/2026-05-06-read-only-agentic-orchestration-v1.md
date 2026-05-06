# Read-Only Agentic Orchestration V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract read-only agentic routing and orchestration helpers from `runtime/run_query.py` into focused agent modules, while preserving current baseline behavior and making Phase 1 measurable.

**Architecture:** Keep retrieval, ranking, context assembly, and generation owned by `runtime/run_query.py` for this slice. Move pure agentic routing and read-only planning/orchestration helpers into `src/homllm/agent/`, then call them from the runtime entrypoint. This avoids a risky full runtime rewrite while creating clean seams for later verification and patch-capable modes.

**Tech Stack:** Python dataclasses, existing HOM-LLM config types, existing `Intent` enum, existing generation provider interfaces, pytest.

---

## File Structure

- Create `src/homllm/agent/router.py`: resolve configured agentic mode, map runtime intent to `TaskClass`, and optionally route simple tasks to single-pass while sending complex tasks to read-only agentic mode.
- Create `src/homllm/agent/orchestrator.py`: hold read-only planner contracts and pure helper functions currently embedded in `runtime/run_query.py`.
- Modify `src/homllm/agent/__init__.py`: export the new router and orchestrator symbols used by runtime and tests.
- Modify `runtime/run_query.py`: remove duplicated agentic helper definitions and import them from `src/homllm/agent/`.
- Create `tests/unit/test_agent_router.py`: unit-test disabled mode, default-mode compatibility, selective routing, and invalid config fallback.
- Create `tests/unit/test_agent_orchestrator.py`: unit-test override sanitization, follow-up override broadening, pass signatures, prompt construction, and config replacement.
- Create `docs/agentic/read-only-orchestration-v1-validation.md`: record the validation commands and known regression classes for this milestone.

## Task 1: Add Router Module

**Files:**
- Create: `src/homllm/agent/router.py`
- Modify: `src/homllm/agent/__init__.py`
- Test: `tests/unit/test_agent_router.py`

- [ ] **Step 1: Write failing router tests**

Create `tests/unit/test_agent_router.py`:

```python
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
```

- [ ] **Step 2: Run router tests to verify they fail**

Run:

```powershell
python -m pytest tests/unit/test_agent_router.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'homllm.agent.router'`.

- [ ] **Step 3: Implement `src/homllm/agent/router.py`**

Create `src/homllm/agent/router.py`:

```python
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
```

- [ ] **Step 4: Export router symbols**

Modify `src/homllm/agent/__init__.py`:

```python
from homllm.agent.router import (
    RouteDecision,
    intent_to_task_class,
    resolve_agentic_mode,
    route_agentic_mode,
)
```

Add these names to `__all__`:

```python
    "RouteDecision",
    "intent_to_task_class",
    "resolve_agentic_mode",
    "route_agentic_mode",
```

- [ ] **Step 5: Run router tests to verify they pass**

Run:

```powershell
python -m pytest tests/unit/test_agent_router.py -q
```

Expected: PASS for all tests in `tests/unit/test_agent_router.py`.

- [ ] **Step 6: Commit router extraction**

Run:

```powershell
git add src/homllm/agent/router.py src/homllm/agent/__init__.py tests/unit/test_agent_router.py
git commit -m "Add agentic routing policy"
```

Expected: commit succeeds and includes only the router module, exports, and router tests.

## Task 2: Extract Read-Only Orchestrator Helpers

**Files:**
- Create: `src/homllm/agent/orchestrator.py`
- Modify: `src/homllm/agent/__init__.py`
- Test: `tests/unit/test_agent_orchestrator.py`

- [ ] **Step 1: Write failing orchestrator helper tests**

Create `tests/unit/test_agent_orchestrator.py`:

```python
from dataclasses import dataclass

from homllm.agent.orchestrator import (
    AgenticIterationSnapshot,
    ReadOnlyPlannerDecision,
    agentic_pass_signature,
    apply_read_only_iteration_retrieval_config,
    build_read_only_planner_prompt,
    default_followup_overrides,
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
    snapshot = AgenticIterationSnapshot(
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
```

- [ ] **Step 2: Run orchestrator tests to verify they fail**

Run:

```powershell
python -m pytest tests/unit/test_agent_orchestrator.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'homllm.agent.orchestrator'`.

- [ ] **Step 3: Implement `src/homllm/agent/orchestrator.py`**

Create `src/homllm/agent/orchestrator.py`:

```python
"""Read-only orchestration helpers for HOM-LLM agentic mode."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Any

from homllm.generation.interfaces import ModelConfig, ProviderRequest
from homllm.generation.parser import ResilientJSONParser


@dataclass(frozen=True)
class AgenticIterationSnapshot:
    """Compact trace for one read-only agentic iteration."""

    iteration: int
    retrieval_overrides: dict
    retrieval_candidates: int
    ranking_candidates: int
    context_blocks: int
    context_tokens: int
    context_budget: int
    insufficiency_detected: bool
    planner_action: str
    planner_reason: str
    planner_parse_ok: bool
    planner_raw_text: str
    repeated_signature_count: int
    signature: str


@dataclass(frozen=True)
class ReadOnlyPlannerDecision:
    """Planner output for one read-only agentic step."""

    action: str
    reason: str
    overrides: dict
    parse_ok: bool
    raw_text: str

    @classmethod
    def answer(cls, reason: str, raw_text: str = "", parse_ok: bool = True) -> "ReadOnlyPlannerDecision":
        """Build a canonical answer decision."""
        return cls(
            action="answer",
            reason=reason,
            overrides={},
            parse_ok=parse_ok,
            raw_text=raw_text,
        )

    @classmethod
    def retrieve_context(
        cls,
        reason: str,
        overrides: dict | None = None,
        raw_text: str = "",
        parse_ok: bool = True,
    ) -> "ReadOnlyPlannerDecision":
        """Build a canonical retrieve-context decision."""
        return cls(
            action="retrieve_context",
            reason=reason,
            overrides=overrides or {},
            parse_ok=parse_ok,
            raw_text=raw_text,
        )


def normalize_planner_action(value: str) -> str:
    """Normalize planner action into canonical values."""
    action = str(value or "").strip().lower()
    if action in {"retrieve_context", "retrieve", "search", "continue"}:
        return "retrieve_context"
    return "answer"


def sanitize_planner_overrides(raw_overrides: dict) -> dict:
    """Validate and clamp planner-proposed retrieval overrides."""
    if not isinstance(raw_overrides, dict):
        return {}

    numeric_specs = {
        "bm25_top_k": {"kind": "int", "min": 1, "max": 500},
        "vector_top_k": {"kind": "int", "min": 1, "max": 500},
        "post_merge_candidates": {"kind": "int", "min": 1, "max": 800},
        "precision_recovery_scan_candidates": {"kind": "int", "min": 1, "max": 100},
        "precision_recovery_max_additions": {"kind": "int", "min": 0, "max": 32},
        "coverage_recovery_max_additions": {"kind": "int", "min": 0, "max": 32},
        "precision_recovery_min_confidence": {"kind": "float", "min": 0.0, "max": 1.0},
    }

    sanitized: dict[str, int | float] = {}
    for key, spec in numeric_specs.items():
        if key not in raw_overrides:
            continue
        try:
            if spec["kind"] == "int":
                value = int(raw_overrides[key])
            else:
                value = float(raw_overrides[key])
        except (TypeError, ValueError):
            continue

        min_value = spec["min"]
        max_value = spec["max"]
        value = max(min_value, min(max_value, value))
        if spec["kind"] == "float":
            value = round(float(value), 3)
        sanitized[key] = value

    return sanitized


def default_followup_overrides(base_config, iteration: int) -> dict:
    """Fallback retrieval broadening when planner requests more context without overrides."""
    factor = max(1, min(iteration, 3))
    bm25_top_k = max(1, int(base_config.bm25_top_k * (1.0 + 0.2 * factor)))
    vector_top_k = max(1, int(base_config.vector_top_k * (1.0 + 0.2 * factor)))
    post_merge_candidates = int(base_config.post_merge_candidates or 0)
    if post_merge_candidates > 0:
        post_merge_candidates += 10 * factor
    else:
        post_merge_candidates = max(bm25_top_k, vector_top_k)

    return {
        "bm25_top_k": bm25_top_k,
        "vector_top_k": vector_top_k,
        "post_merge_candidates": post_merge_candidates,
        "precision_recovery_scan_candidates": max(
            1,
            int(base_config.precision_recovery_scan_candidates + (2 * factor)),
        ),
        "coverage_recovery_max_additions": max(
            0,
            int(base_config.coverage_recovery_max_additions + factor),
        ),
        "precision_recovery_min_confidence": round(
            max(
                0.55,
                float(base_config.precision_recovery_min_confidence) - (0.05 * factor),
            ),
            3,
        ),
    }


def apply_read_only_iteration_retrieval_config(base_config, raw_overrides: dict):
    """Apply validated retrieval overrides to config for one iteration."""
    overrides = sanitize_planner_overrides(raw_overrides)
    if not overrides:
        return base_config, {}
    iteration_config = replace(base_config, **overrides)
    return iteration_config, overrides


def build_read_only_planner_prompt(
    query: str,
    iteration: int,
    max_iterations: int,
    last_snapshot: AgenticIterationSnapshot,
) -> str:
    """Build planner prompt for choosing next read-only action."""
    summary_payload = {
        "query": query,
        "iteration": iteration,
        "max_iterations": max_iterations,
        "remaining_iterations": max(0, max_iterations - iteration),
        "retrieval_candidates": last_snapshot.retrieval_candidates,
        "ranking_candidates": last_snapshot.ranking_candidates,
        "context_blocks": last_snapshot.context_blocks,
        "context_tokens": last_snapshot.context_tokens,
        "context_budget": last_snapshot.context_budget,
        "repeated_signature_count": last_snapshot.repeated_signature_count,
        "signature": last_snapshot.signature,
    }
    summary_json = json.dumps(summary_payload, indent=2, ensure_ascii=False)
    return (
        "You are a planning controller for code-retrieval QA.\n"
        "Decide whether another retrieval/ranking/context pass is needed before answering.\n"
        "Return ONLY strict JSON with this schema:\n"
        "{\n"
        '  "action": "retrieve_context" | "answer",\n'
        '  "reason": "short reason",\n'
        '  "overrides": {\n'
        '    "bm25_top_k": int,\n'
        '    "vector_top_k": int,\n'
        '    "post_merge_candidates": int,\n'
        '    "precision_recovery_scan_candidates": int,\n'
        '    "precision_recovery_max_additions": int,\n'
        '    "coverage_recovery_max_additions": int,\n'
        '    "precision_recovery_min_confidence": float\n'
        "  }\n"
        "}\n"
        "Rules:\n"
        "- Use action=retrieve_context when more evidence breadth/depth is needed.\n"
        "- Use action=answer only when current context is likely sufficient.\n"
        "- If action=answer, set overrides to {}.\n"
        "- Do not emit markdown.\n\n"
        "Current state:\n"
        f"{summary_json}"
    )


def invoke_read_only_planner(
    provider,
    model_name: str,
    query: str,
    iteration: int,
    max_iterations: int,
    last_snapshot: AgenticIterationSnapshot,
) -> ReadOnlyPlannerDecision:
    """Invoke planner model and return validated next action."""
    prompt = build_read_only_planner_prompt(
        query=query,
        iteration=iteration,
        max_iterations=max_iterations,
        last_snapshot=last_snapshot,
    )
    request = ProviderRequest(
        prompt=prompt,
        model=model_name,
        config=ModelConfig(temperature=0.0, max_output_tokens=300),
        stream=False,
    )
    parser = ResilientJSONParser()
    try:
        response = provider.invoke_sync(request)
        raw_text = response.text or ""
    except Exception as exc:
        return ReadOnlyPlannerDecision.answer(
            reason=f"planner_error:{exc.__class__.__name__}",
            raw_text=str(exc),
            parse_ok=False,
        )

    parsed, _corrections = parser.parse(raw_text)
    if not isinstance(parsed, dict):
        import re

        action_match = re.search(
            r'"action"\s*:\s*"([^"]+)"',
            raw_text,
            flags=re.IGNORECASE,
        )
        if action_match:
            action = normalize_planner_action(action_match.group(1))
            if iteration >= max_iterations:
                action = "answer"
            if action == "retrieve_context":
                return ReadOnlyPlannerDecision.retrieve_context(
                    reason="planner_partial_parse_action_only",
                    parse_ok=False,
                    raw_text=raw_text,
                )
            return ReadOnlyPlannerDecision.answer(
                reason="planner_partial_parse_action_only",
                parse_ok=False,
                raw_text=raw_text,
            )
        fallback_action = "retrieve_context" if iteration < max_iterations else "answer"
        if fallback_action == "retrieve_context":
            return ReadOnlyPlannerDecision.retrieve_context(
                reason="planner_parse_failed_default_retrieve_context",
                parse_ok=False,
                raw_text=raw_text,
            )
        return ReadOnlyPlannerDecision.answer(
            reason="planner_parse_failed_default_answer",
            parse_ok=False,
            raw_text=raw_text,
        )

    action = normalize_planner_action(parsed.get("action", "answer"))
    reason = str(parsed.get("reason", "") or "").strip() or "planner_decision"
    overrides = sanitize_planner_overrides(parsed.get("overrides", {}))
    if action == "retrieve_context":
        return ReadOnlyPlannerDecision.retrieve_context(
            reason=reason,
            overrides=overrides,
            parse_ok=True,
            raw_text=raw_text,
        )
    return ReadOnlyPlannerDecision.answer(
        reason=reason,
        parse_ok=True,
        raw_text=raw_text,
    )


def agentic_pass_signature(retrieval_result, ranking_output, context_artifact) -> str:
    """Create compact signature for no-progress detection."""
    retrieval_candidates = len(getattr(retrieval_result, "candidates", []) or [])
    ranking_candidates = (
        len(getattr(ranking_output, "ranked_candidates", []) or [])
        if ranking_output is not None
        else 0
    )
    context_blocks = (
        len(getattr(context_artifact, "blocks", []) or [])
        if context_artifact is not None
        else 0
    )
    context_tokens = (
        int(getattr(context_artifact, "used_tokens", 0) or 0)
        if context_artifact is not None
        else 0
    )
    return (
        f"ret={retrieval_candidates}|rank={ranking_candidates}|"
        f"blocks={context_blocks}|tok_bucket={context_tokens // 100}"
    )
```

- [ ] **Step 4: Export orchestrator symbols**

Modify `src/homllm/agent/__init__.py`:

```python
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
```

Add these names to `__all__`:

```python
    "AgenticIterationSnapshot",
    "ReadOnlyPlannerDecision",
    "agentic_pass_signature",
    "apply_read_only_iteration_retrieval_config",
    "build_read_only_planner_prompt",
    "default_followup_overrides",
    "invoke_read_only_planner",
    "normalize_planner_action",
    "sanitize_planner_overrides",
```

- [ ] **Step 5: Run orchestrator tests to verify they pass**

Run:

```powershell
python -m pytest tests/unit/test_agent_orchestrator.py -q
```

Expected: PASS for all tests in `tests/unit/test_agent_orchestrator.py`.

- [ ] **Step 6: Commit orchestrator helper extraction**

Run:

```powershell
git add src/homllm/agent/orchestrator.py src/homllm/agent/__init__.py tests/unit/test_agent_orchestrator.py
git commit -m "Extract read-only orchestration helpers"
```

Expected: commit succeeds and includes only orchestrator helpers, exports, and tests.

## Task 3: Wire Runtime to Router and Orchestrator Modules

**Files:**
- Modify: `runtime/run_query.py`
- Test: `tests/unit/test_agent_router.py`
- Test: `tests/unit/test_agent_orchestrator.py`

- [ ] **Step 1: Update imports in `runtime/run_query.py`**

Replace the current `homllm.agent` import block with:

```python
from homllm.agent import (
    AgenticIterationSnapshot,
    AgenticMode,
    EvidenceAttempt,
    EvidenceState,
    LoopBudget,
    ReadOnlyPlannerDecision,
    RepetitionGuard,
    StopReason,
    TaskState,
    agentic_pass_signature,
    apply_read_only_iteration_retrieval_config,
    default_followup_overrides,
    invoke_read_only_planner,
    route_agentic_mode,
)
```

Keep `from dataclasses import asdict, replace` because `runtime/run_query.py` still uses both outside the extracted helper block.

- [ ] **Step 2: Remove imports no longer needed by runtime**

Remove these imports from `runtime/run_query.py` if no longer referenced after helper deletion:

```python
from dataclasses import dataclass
from homllm.generation.interfaces import ModelConfig, ProviderRequest
from homllm.generation.parser import ResilientJSONParser
```

Keep `from enum import Enum` because `_write_agentic_trace_artifact` still serializes enum values unless that helper is moved later.

- [ ] **Step 3: Delete duplicated helper definitions from runtime**

Delete the complete local definitions for these symbols currently near the top of `runtime/run_query.py`:

```text
AgenticIterationSnapshot
ReadOnlyPlannerDecision
_intent_to_task_class
_resolve_agentic_mode
_normalize_planner_action
_sanitize_planner_overrides
_default_followup_overrides
_apply_read_only_iteration_retrieval_config
_build_read_only_planner_prompt
_invoke_read_only_planner
_agentic_pass_signature
```

Do not move `_write_agentic_trace_artifact` in this task. It writes runtime artifacts and depends on `print_telemetry`, so it should remain in `runtime/run_query.py` for this slice.

- [ ] **Step 4: Replace mode resolution in runtime**

Replace:

```python
        agentic_mode = _resolve_agentic_mode(agentic_config.default_mode)
        read_only_agentic_enabled = bool(
            agentic_config.enabled and agentic_mode == AgenticMode.READ_ONLY_AGENTIC
        )
```

with:

```python
        route_decision = route_agentic_mode(
            agentic_config=agentic_config,
            intent=intent,
            query=args.query,
        )
        agentic_mode = route_decision.mode
        read_only_agentic_enabled = bool(
            agentic_config.enabled and agentic_mode == AgenticMode.READ_ONLY_AGENTIC
        )
```

- [ ] **Step 5: Replace task class assignment**

Replace:

```python
            task_class=_intent_to_task_class(intent),
```

with:

```python
            task_class=route_decision.task_class,
```

- [ ] **Step 6: Replace helper calls with imported names**

Replace each call to `_apply_read_only_iteration_retrieval_config` with `apply_read_only_iteration_retrieval_config`.

Replace each call to `_agentic_pass_signature` with `agentic_pass_signature`.

Replace each call to `_invoke_read_only_planner` with `invoke_read_only_planner`.

Replace each call to `_default_followup_overrides` with `default_followup_overrides`.

- [ ] **Step 7: Use planner decision constructors for simple local decisions**

Replace local one-off answer decisions like:

```python
planner_decision = ReadOnlyPlannerDecision(
    action="answer",
    reason="single_pass_mode",
    overrides={},
    parse_ok=True,
    raw_text="",
)
```

with:

```python
planner_decision = ReadOnlyPlannerDecision.answer("single_pass_mode")
```

Replace retrieve-context decisions like:

```python
planner_decision = ReadOnlyPlannerDecision(
    action="retrieve_context",
    reason="missing_ranking_or_context_artifact",
    overrides={},
    parse_ok=True,
    raw_text="",
)
```

with:

```python
planner_decision = ReadOnlyPlannerDecision.retrieve_context(
    "missing_ranking_or_context_artifact"
)
```

- [ ] **Step 8: Add route reason to iteration telemetry**

In the `print_telemetry` call whose first argument is `"AGENTIC_ITERATION"`, add:

```python
                route_reason=route_decision.reason,
```

Expected: trace logs show why a query used single-pass or read-only agentic mode.

- [ ] **Step 9: Run focused tests**

Run:

```powershell
python -m pytest tests/unit/test_agent_router.py tests/unit/test_agent_orchestrator.py -q
```

Expected: PASS.

- [ ] **Step 10: Run import smoke test**

Run:

```powershell
python -c "import runtime.run_query; import homllm.agent.router; import homllm.agent.orchestrator; print('imports ok')"
```

Expected output:

```text
imports ok
```

- [ ] **Step 11: Commit runtime wiring**

Run:

```powershell
git add runtime/run_query.py
git commit -m "Wire runtime to agentic router and orchestrator"
```

Expected: commit succeeds and includes only `runtime/run_query.py`.

## Task 4: Add Validation Runbook for Read-Only Orchestration V1

**Files:**
- Create: `docs/agentic/read-only-orchestration-v1-validation.md`

- [ ] **Step 1: Create validation docs directory**

Run:

```powershell
New-Item -ItemType Directory -Force -Path docs\agentic | Out-Null
```

Expected: `docs/agentic` exists.

- [ ] **Step 2: Write validation runbook**

Create `docs/agentic/read-only-orchestration-v1-validation.md`:

````markdown
# Read-Only Orchestration V1 Validation

## Purpose

This runbook validates that read-only agentic orchestration is clean, measured, and non-regressing before HOM-LLM moves toward execution or patch-capable modes.

## Unit Verification

Run:

```powershell
python -m pytest tests/unit/test_agent_router.py tests/unit/test_agent_orchestrator.py -q
```

Expected:

- all router tests pass
- all orchestrator helper tests pass
- no provider API keys are required

## Import Smoke Test

Run:

```powershell
python -c "import runtime.run_query; import homllm.agent.router; import homllm.agent.orchestrator; print('imports ok')"
```

Expected:

```text
imports ok
```

## Existing Canary Compatibility

Existing canary configs that set `agentic.enabled: true` and `agentic.default_mode: read_only_agentic` but leave `agentic.router_enabled: false` should keep routing all selected queries through read-only agentic mode.

Compatibility condition:

- router disabled means `router_disabled_default_mode`
- no old canary silently changes from read-only agentic to single-pass

## Selective Router Probe

Create a temporary config variant that sets:

```yaml
agentic:
  enabled: true
  default_mode: read_only_agentic
  router_enabled: true
  default_permission_mode: read_only
  loop:
    read_only_max_iterations: 3
    max_repeated_signature: 2
    max_command_failures: 0
```

Expected routing:

- short explain/search tasks stay single-pass
- debug, refactor, implement, and complex explain tasks use read-only agentic mode

## Known Regression Classes

These query classes require special attention before promotion:

- partial failure and at-least-once semantics
- optimizer rule synthesis with timing and plan caching
- stress test outcome synthesis

Observed failure pattern:

The read-only agentic path can become more generic or less synthesized than the baseline. The next fix should improve sufficiency, synthesis, and verification gates rather than adding broader autonomy.

## Promotion Gate

Do not move to execution mode until:

- selected hard tasks improve or match baseline
- simple explain/search tasks do not regress
- agentic trace artifacts are written for read-only runs
- route decisions are visible in telemetry
- the three known regression classes are either fixed or documented with an explicit acceptance decision
````

- [ ] **Step 3: Commit validation runbook**

Run:

```powershell
git add docs/agentic/read-only-orchestration-v1-validation.md
git commit -m "Document read-only orchestration validation"
```

Expected: commit succeeds and includes only the validation runbook.

## Task 5: Final Verification Before Handoff

**Files:**
- Verify: `src/homllm/agent/router.py`
- Verify: `src/homllm/agent/orchestrator.py`
- Verify: `runtime/run_query.py`
- Verify: `tests/unit/test_agent_router.py`
- Verify: `tests/unit/test_agent_orchestrator.py`
- Verify: `docs/agentic/read-only-orchestration-v1-validation.md`

- [ ] **Step 1: Run focused unit suite**

Run:

```powershell
python -m pytest tests/unit/test_agent_router.py tests/unit/test_agent_orchestrator.py -q
```

Expected: PASS.

- [ ] **Step 2: Run import smoke test**

Run:

```powershell
python -c "import runtime.run_query; import homllm.agent; print('agentic imports ok')"
```

Expected output:

```text
agentic imports ok
```

- [ ] **Step 3: Inspect git status**

Run:

```powershell
git status --short
```

Expected: only pre-existing unrelated dirty files remain, or no output if the implementation branch is clean.

- [ ] **Step 4: Summarize remaining milestone work**

Add this summary to the implementation handoff message:

```text
Read-only routing and orchestration helpers are extracted and unit-tested.
Runtime still owns the actual retrieval/ranking/context loop.
Next work after this slice is regression analysis for the three known failed query classes.
Execution and patch-capable modes remain blocked until read-only v1 is non-regressing.
```
