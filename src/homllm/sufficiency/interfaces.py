"""
Intent-Gated Sufficiency Layer — Interfaces and output contract.

Read-only diagnostic layer. No LLM calls, no context mutation, no retrieval/ranking changes.
Semantic equivalence to the architectural plan output contract is required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# --- Intent and axes (from plan 5.1) ---

IntentType = Literal["ARCHITECTURAL", "IMPLEMENTATION", "BEHAVIORAL", "UNKNOWN"]
AxisType = Literal["SEMANTIC", "RULE", "STRUCTURAL"]
VerdictType = Literal["SUFFICIENT", "PROBABLY_SUFFICIENT", "INSUFFICIENT"]
LabelType = Literal["SUFFICIENT", "INSUFFICIENT"]


@dataclass(frozen=True)
class IntentResult:
    """
    Query intent classification result (non-LLM).
    Determines which sufficiency axes are mandatory and whether early exit is allowed.
    """

    intent: IntentType
    mandatory_axes: tuple[AxisType, ...]
    early_exit_allowed: bool


@dataclass(frozen=True)
class SignalResult:
    """Single sufficiency signal: score in [0, 1] and label."""

    score: float
    label: LabelType


@dataclass(frozen=True)
class SufficiencyResult:
    """
    Final sufficiency verdict and attribution (plan §7 output contract).
    Machine-readable, fully auditable. No averaging, no voting.
    """

    final_verdict: VerdictType
    deciding_factor: AxisType | None  # Which axis caused veto; None if SUFFICIENT
    intent: IntentType
    signals: dict[str, SignalResult]  # keys: "semantic", "rule", "structural"

    def to_dict(self) -> dict:
        """Emit contract for logging/post-mortem."""
        return {
            "final_verdict": self.final_verdict,
            "deciding_factor": self.deciding_factor,
            "intent": self.intent,
            "signals": {
                k: {"score": round(v.score, 4), "label": v.label}
                for k, v in self.signals.items()
            },
        }
