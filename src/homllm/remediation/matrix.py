"""
Action selection matrix (spec §6): deterministic mapping from deciding factor to allowed actions.

No scoring; no inference. If no mapping exists → no action.
Ordering (§7): Structural first, Token second, Prompt last. At most one action per axis per run.
"""

from __future__ import annotations

from homllm.remediation.interfaces import (
    ActionType,
    DecidingFactorType,
    RemediationAction,
)

# Spec §6: Deciding Factor → single allowed action (one per axis)
# STRUCTURAL → Structural Absence → Retrieval Expansion
# RULE → Wrong Subsystem → Retrieval Re-target
# SEMANTIC → Fragmentation → Token Budget Increase (Explanation Gap → Prompt Strategy; we use Token as primary)
_DECIDING_FACTOR_TO_ACTION: dict[DecidingFactorType, tuple[ActionType, str, str]] = {
    "STRUCTURAL": (
        "RETRIEVAL_EXPANSION",
        "STRUCTURAL",
        "Expand retrieval scope (e.g. README/docs, parent dirs) to address structural absence.",
    ),
    "RULE": (
        "RETRIEVAL_RE_TARGET",
        "RULE",
        "Re-target retrieval to correct subsystem / entity coverage.",
    ),
    "SEMANTIC": (
        "TOKEN_BUDGET_INCREASE",
        "SEMANTIC",
        "Increase token ceiling or allow multi-pass context assembly to reduce fragmentation.",
    ),
}

# Historical Fragility (spec §6): not an axis; triggered by fragility_flag
_FRAGILITY_ACTION: tuple[ActionType, str, str] = (
    "RETRY_ESCALATION",
    "HISTORICAL_FRAGILITY",
    "Retry with expanded constraints or surface partial answer + warning; defer to review if repeated MISALIGNED.",
)

# Ordering (§7): Structural fixes first, Token second, Prompt last
_ACTION_PRIORITY: tuple[ActionType, ...] = (
    "RETRIEVAL_EXPANSION",
    "RETRIEVAL_RE_TARGET",
    "TOKEN_BUDGET_INCREASE",
    "PROMPT_STRATEGY",
    "RETRY_ESCALATION",
)


def _priority_order(action_type: ActionType) -> int:
    """Lower index = higher priority (applied first)."""
    try:
        return _ACTION_PRIORITY.index(action_type)
    except ValueError:
        return len(_ACTION_PRIORITY)


def allowed_action_for_deciding_factor(
    deciding_factor: DecidingFactorType,
) -> RemediationAction | None:
    """
    Return the single allowed action for this deciding factor (spec §6).
    If no mapping exists, return None.
    """
    entry = _DECIDING_FACTOR_TO_ACTION.get(deciding_factor)
    if not entry:
        return None
    action_type, trigger, effect = entry
    return RemediationAction(
        action_type=action_type,
        trigger_signal=trigger,
        expected_effect=effect,
        actual_outcome=None,
    )


def action_for_fragility() -> RemediationAction:
    """Return the Retry/Escalation action for historical fragility (spec §6)."""
    action_type, trigger, effect = _FRAGILITY_ACTION
    return RemediationAction(
        action_type=action_type,
        trigger_signal=trigger,
        expected_effect=effect,
        actual_outcome=None,
    )


def sort_actions_by_priority(actions: list[RemediationAction]) -> list[RemediationAction]:
    """Order actions per spec §7: Structural first, Token second, Prompt last."""
    return sorted(actions, key=lambda a: _priority_order(a.action_type))


__all__ = [
    "action_for_fragility",
    "allowed_action_for_deciding_factor",
    "sort_actions_by_priority",
]
