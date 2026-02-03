"""
Structural Explanation Gap Detection — Output contract and types (Problem 4).

Read-only diagnostic. Advisory guidance only. No generation, retrieval, or prompt mutation.
Exactly one label; escalation only upward; conservative bias.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# --- Depth recommendation (exactly one; spec §1) ---
DepthLabelType = Literal["SHALLOW_OK", "DETAILED_REQUIRED", "EXAMPLE_RECOMMENDED"]

# --- Intent classes for intent-to-depth table (spec §6) ---
DepthIntentType = Literal["FACTUAL", "EXPLANATORY", "DEBUGGING", "ILLUSTRATIVE"]

# Severity order: EXAMPLE_RECOMMENDED > DETAILED_REQUIRED > SHALLOW_OK
_SEVERITY_ORDER: tuple[DepthLabelType, ...] = (
    "EXAMPLE_RECOMMENDED",
    "DETAILED_REQUIRED",
    "SHALLOW_OK",
)


def severity_rank(label: DepthLabelType) -> int:
    """Lower index = higher severity (escalation)."""
    return _SEVERITY_ORDER.index(label)


def max_severity(a: DepthLabelType, b: DepthLabelType) -> DepthLabelType:
    """Return the more severe (higher escalation) of the two. No downgrade."""
    return a if severity_rank(a) <= severity_rank(b) else b


@dataclass(frozen=True)
class SignalOutput:
    """Per-signal output for auditability (spec §8)."""

    signal_name: str
    label: DepthLabelType | None  # None = no trigger
    trigger: str  # e.g. "Rule(why)", "History(expand_pct)", "Embedding(explanation)"
    score_or_note: str = ""


@dataclass(frozen=True)
class ExplanationGapResult:
    """
    Output contract (spec §1, §8).

    Advisory only. Exactly one final label; deciding trigger; confidence; evidence volume.
    """

    label: DepthLabelType
    confidence: float
    evidence_volume: int
    rationale: str
    deciding_trigger: str
    per_signal_outputs: tuple[SignalOutput, ...] = ()
    cold_start: bool = False

    def to_dict(self) -> dict:
        """Machine-readable for logging and audit."""
        return {
            "label": self.label,
            "confidence": self.confidence,
            "evidence_volume": self.evidence_volume,
            "rationale": self.rationale,
            "deciding_trigger": self.deciding_trigger,
            "per_signal_outputs": [
                {
                    "signal_name": s.signal_name,
                    "label": s.label,
                    "trigger": s.trigger,
                    "score_or_note": s.score_or_note,
                }
                for s in self.per_signal_outputs
            ],
            "cold_start": self.cold_start,
        }


@dataclass(frozen=True)
class HistoryDepthStats:
    """
    Read-only historical depth stats per bucket (spec §4.4).

    Optional. Cold-start when absent → conservative escalation.
    """

    runs_in_bucket: int
    pct_expanded_or_manual: float  # 0..1
    pct_shallow_complaints: float  # 0..1


__all__ = [
    "DepthIntentType",
    "DepthLabelType",
    "ExplanationGapResult",
    "HistoryDepthStats",
    "SignalOutput",
    "max_severity",
    "severity_rank",
]
