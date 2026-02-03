"""
Stage 1 — Rule-based pattern matching (spec §4.1, §5).

Deterministic triggers: keywords, question form, debugging markers.
Most severe trigger dominates. No downgrade. Intent-to-depth default when no rule fires.
"""

from __future__ import annotations

from homllm.explanation_gap.constants import (
    INTENT_DEFAULT,
    PATTERNS_DEBUG,
    PATTERNS_DETAILED,
    PATTERNS_EXAMPLE,
    RULE_PATTERNS,
)
from homllm.explanation_gap.interfaces import (
    DepthIntentType,
    DepthLabelType,
    SignalOutput,
    max_severity,
)


def classify_depth_intent(query: str) -> DepthIntentType:
    """
    Classify query into intent class for default (spec §6).
    Order: Illustrative > Explanatory/Debugging > Factual. Ambiguity → escalate (conservative).
    """
    q = query.strip()
    if not q:
        return "FACTUAL"
    if PATTERNS_EXAMPLE.search(q):
        return "ILLUSTRATIVE"
    if PATTERNS_DETAILED.search(q):
        return "EXPLANATORY"
    if PATTERNS_DEBUG.search(q):
        return "DEBUGGING"
    return "FACTUAL"


def rule_based_depth(query: str) -> tuple[DepthLabelType, str, list[SignalOutput]]:
    """
    Stage 1 rule-based escalation. Most severe trigger dominates (spec §5).
    Returns (label, deciding_trigger, per_signal_outputs).
    No downgrade; if no rule fires, use intent default.
    """
    intent = classify_depth_intent(query)
    default_label = INTENT_DEFAULT[intent]
    trigger_label: DepthLabelType | None = None
    deciding_trigger = f"IntentDefault({intent})"

    for label, pattern in RULE_PATTERNS:
        if pattern.search(query):
            trigger_label = max_severity(trigger_label, label) if trigger_label else label

    if trigger_label is not None:
        final = trigger_label
        deciding_trigger = f"Rule({trigger_label})"
    else:
        final = default_label
        deciding_trigger = f"IntentDefault({intent})"

    # Per-signal for audit: rules
    rule_signal = SignalOutput(
        signal_name="rule_patterns",
        label=final,
        trigger=deciding_trigger,
        score_or_note=f"intent={intent}",
    )
    return final, deciding_trigger, [rule_signal]


__all__ = ["classify_depth_intent", "rule_based_depth"]
