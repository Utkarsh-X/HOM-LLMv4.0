"""Read-only agentic orchestration helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace


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
    def answer(
        cls,
        reason: str,
        *,
        parse_ok: bool = True,
        raw_text: str = "",
    ) -> "ReadOnlyPlannerDecision":
        """Create a safe answer decision without retrieval overrides."""
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
        *,
        overrides: dict | None = None,
        parse_ok: bool = True,
        raw_text: str = "",
    ) -> "ReadOnlyPlannerDecision":
        """Create a retrieve-context decision with validated overrides."""
        return cls(
            action="retrieve_context",
            reason=reason,
            overrides=sanitize_planner_overrides(overrides or {}),
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
            1, int(base_config.precision_recovery_scan_candidates + (2 * factor))
        ),
        "coverage_recovery_max_additions": max(
            0, int(base_config.coverage_recovery_max_additions + factor)
        ),
        "precision_recovery_min_confidence": round(
            max(0.55, float(base_config.precision_recovery_min_confidence) - (0.05 * factor)),
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
    """Invoke planner model and return a validated next action."""
    from homllm.generation.interfaces import ModelConfig, ProviderRequest
    from homllm.generation.parser import ResilientJSONParser

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
        parsed, _corrections = parser.parse(raw_text)
    except Exception as exc:
        return ReadOnlyPlannerDecision.answer(
            f"planner_error:{exc.__class__.__name__}",
            parse_ok=False,
            raw_text=str(exc),
        )

    if not isinstance(parsed, dict):
        action_match = re.search(
            r'"action"\s*:\s*"([^"]+)"',
            raw_text,
            flags=re.IGNORECASE,
        )
        if action_match:
            action = normalize_planner_action(action_match.group(1))
            if iteration >= max_iterations:
                action = "answer"
            return ReadOnlyPlannerDecision(
                action=action,
                reason="planner_partial_parse_action_only",
                overrides={},
                parse_ok=False,
                raw_text=raw_text,
            )

        fallback_action = "retrieve_context" if iteration < max_iterations else "answer"
        return ReadOnlyPlannerDecision(
            action=fallback_action,
            reason=f"planner_parse_failed_default_{fallback_action}",
            overrides={},
            parse_ok=False,
            raw_text=raw_text,
        )

    action = normalize_planner_action(parsed.get("action", "answer"))
    reason = str(parsed.get("reason", "") or "").strip()
    if not reason:
        reason = "planner_decision"
    overrides = sanitize_planner_overrides(parsed.get("overrides", {}))
    if action == "answer" or iteration >= max_iterations:
        return ReadOnlyPlannerDecision.answer(reason, raw_text=raw_text)
    return ReadOnlyPlannerDecision.retrieve_context(
        reason,
        overrides=overrides,
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
