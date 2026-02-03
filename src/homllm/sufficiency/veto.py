"""
Veto Resolution (plan §6).

Conjunctive logic: one hard failure blocks SUFFICIENT.
No averaging. No voting. Explicit veto hierarchy.
"""

from __future__ import annotations

from homllm.sufficiency.interfaces import (
    AxisType,
    IntentResult,
    SignalResult,
    SufficiencyResult,
    VerdictType,
)

# Hard vetoes only: structural, rule (plan 6.1). Semantic is soft veto only.
_HARD_VETO_ORDER: tuple[AxisType, ...] = ("STRUCTURAL", "RULE")


def resolve_veto(
    intent_result: IntentResult,
    signals: dict[str, SignalResult],
) -> SufficiencyResult:
    """
    Apply veto hierarchy (AND-logic). No signal can override a hard veto.
    - Structural insufficiency (if mandatory) → Hard veto → INSUFFICIENT
    - Rule/entity insufficiency (if mandatory) → Hard veto → INSUFFICIENT
    - Semantic insufficiency → Soft veto → PROBABLY_SUFFICIENT (if no hard veto)
    - All mandatory pass → SUFFICIENT
    """
    mandatory = set(intent_result.mandatory_axes)
    deciding_factor: AxisType | None = None
    final_verdict: VerdictType = "SUFFICIENT"

    # Check hard vetoes in order (structural → rule → semantic)
    _axis_key: dict[AxisType, str] = {
        "STRUCTURAL": "structural",
        "RULE": "rule",
        "SEMANTIC": "semantic",
    }
    for axis in _HARD_VETO_ORDER:
        if axis not in mandatory:
            continue
        sig = signals.get(_axis_key[axis])
        if sig is None:
            continue
        if sig.label == "INSUFFICIENT":
            deciding_factor = axis
            final_verdict = "INSUFFICIENT"
            break

    # No hard veto; check semantic soft veto
    if final_verdict == "SUFFICIENT" and "SEMANTIC" in mandatory:
        sem = signals.get("semantic")
        if sem and sem.label == "INSUFFICIENT":
            final_verdict = "PROBABLY_SUFFICIENT"
            deciding_factor = "SEMANTIC"

    return SufficiencyResult(
        final_verdict=final_verdict,
        deciding_factor=deciding_factor,
        intent=intent_result.intent,
        signals=signals,
    )


__all__ = ["resolve_veto"]
