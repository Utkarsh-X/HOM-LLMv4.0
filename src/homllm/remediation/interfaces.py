"""
Action & Remediation Layer — Interfaces and contracts (§3, §8).

Consumes Problem‑1 diagnostics only. Does not diagnose.
All actions are procedural, bounded, and attributable to a diagnostic signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# --- Alignment labels (spec §3; maps from P1 verdict) ---
FinalLabelType = Literal["ALIGNED", "PARTIALLY_ALIGNED", "MISALIGNED"]

# --- Deciding factor: axis that caused veto (P1: STRUCTURAL | RULE | SEMANTIC) ---
DecidingFactorType = Literal["STRUCTURAL", "RULE", "SEMANTIC"]

# --- Action types (spec §5, §6) ---
ActionType = Literal[
    "RETRIEVAL_EXPANSION",
    "RETRIEVAL_RE_TARGET",
    "TOKEN_BUDGET_INCREASE",
    "PROMPT_STRATEGY",
    "RETRY_ESCALATION",
]


@dataclass(frozen=True)
class RemediationInput:
    """
    Input contract for Problem‑2 (spec §3).
    Must not infer missing information; absent fields → no action.
    """

    final_label: FinalLabelType
    deciding_factor: DecidingFactorType | None
    intent_class: str  # ARCHITECTURAL | IMPLEMENTATION | BEHAVIORAL | UNKNOWN
    failed_axes: tuple[str, ...]
    # Optional; if absent, not used for selection (spec: default no action)
    negative_evidence: tuple[str, ...] = ()
    confidence: float | None = None
    fragility_flag: bool = False


@dataclass(frozen=True)
class RemediationAction:
    """
    Single corrective action (spec §5, §8).
    Emits action_type, trigger_signal, expected_effect; actual_outcome is post‑hoc.
    """

    action_type: ActionType
    trigger_signal: str  # deciding factor or "HISTORICAL_FRAGILITY"
    expected_effect: str
    actual_outcome: str | None = None  # filled post‑hoc by caller


@dataclass(frozen=True)
class RemediationResult:
    """
    Output of the remediation layer (spec §7 ordering, §8 observability).
    At most one action per axis per run; ordered: Structural → Token → Prompt → Retry.
    """

    actions: tuple[RemediationAction, ...]
    # Cause → effect mapping for logging
    trigger_to_actions: tuple[tuple[str, ActionType], ...]

    def to_dict(self) -> dict:
        """Emit contract for logging / post‑mortem."""
        return {
            "actions": [
                {
                    "action_type": a.action_type,
                    "trigger_signal": a.trigger_signal,
                    "expected_effect": a.expected_effect,
                    "actual_outcome": a.actual_outcome,
                }
                for a in self.actions
            ],
            "trigger_to_actions": list(self.trigger_to_actions),
        }


__all__ = [
    "ActionType",
    "DecidingFactorType",
    "FinalLabelType",
    "RemediationAction",
    "RemediationInput",
    "RemediationResult",
]
