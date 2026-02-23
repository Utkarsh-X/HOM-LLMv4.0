"""
Action & Remediation Pipeline (spec §4–§9).

CURRENT STATUS: Only TOKEN_BUDGET_INCREASE action is wired to runtime.
Structural (re-retrieval) and Prompt (prompt adjustment) actions exist in
the action matrix but are NOT connected. These are reserved for future
agentic system integration where an LLM-based agent with tool utilization
will handle budget, retrieval, and prompt decisions automatically.

Consumes Problem‑1 diagnostic (via RemediationInput). Selects actions by deterministic
matrix; applies ordering and one-action-per-axis limit. Does not diagnose or mutate P1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homllm.remediation.adapter import sufficiency_to_remediation_input
from homllm.remediation.interfaces import (
    ActionType,
    DecidingFactorType,
    RemediationAction,
    RemediationInput,
    RemediationResult,
)
from homllm.remediation.matrix import (
    action_for_fragility,
    allowed_action_for_deciding_factor,
    sort_actions_by_priority,
)

if TYPE_CHECKING:
    from homllm.sufficiency.interfaces import SufficiencyResult


def run_remediation(input_data: RemediationInput) -> RemediationResult:
    """
    Compute corrective actions from a diagnosed context adequacy failure (spec §4).

    - ALIGNED → no action.
    - PARTIALLY_ALIGNED / MISALIGNED → one allowed action per failed axis (spec §7),
      ordered: Structural first, Token second, Prompt last.
    - fragility_flag → add Retry/Escalation once (spec §6).
    - If a field is absent or no mapping exists → no action for that axis (spec §3).
    """
    if input_data.final_label == "ALIGNED":
        return RemediationResult(actions=(), trigger_to_actions=())

    actions: list[RemediationAction] = []
    trigger_to_actions: list[tuple[str, ActionType]] = []

    # One action per failed axis; do not infer missing (spec §3)
    seen_axes: set[str] = set()
    for axis in input_data.failed_axes:
        if axis in seen_axes:
            continue
        factor = _as_deciding_factor(axis)
        if factor is None:
            continue
        action = allowed_action_for_deciding_factor(factor)
        if action is not None:
            actions.append(action)
            trigger_to_actions.append((axis, action.action_type))
            seen_axes.add(axis)

    # Historical fragility: add Retry/Escalation once (spec §6)
    if input_data.fragility_flag:
        fragility_action = action_for_fragility()
        actions.append(fragility_action)
        trigger_to_actions.append((fragility_action.trigger_signal, fragility_action.action_type))

    # Order: Structural first, Token second, Prompt last (spec §7)
    ordered = sort_actions_by_priority(actions)

    return RemediationResult(
        actions=tuple(ordered),
        trigger_to_actions=tuple(trigger_to_actions),
    )


def _as_deciding_factor(axis: str) -> DecidingFactorType | None:
    """Treat axis name as deciding factor only if it matches the contract."""
    if axis in ("STRUCTURAL", "RULE", "SEMANTIC"):
        return axis  # type: ignore[return-value]
    return None


def run_remediation_from_sufficiency(
    sufficiency_result: "SufficiencyResult",
    *,
    fragility_flag: bool = False,
) -> RemediationResult:
    """
    Convenience: run remediation from Problem‑1 SufficiencyResult.
    Equivalent to: run_remediation(sufficiency_to_remediation_input(...)).
    """
    input_data = sufficiency_to_remediation_input(
        sufficiency_result, fragility_flag=fragility_flag
    )
    return run_remediation(input_data)


__all__ = ["run_remediation", "run_remediation_from_sufficiency"]
