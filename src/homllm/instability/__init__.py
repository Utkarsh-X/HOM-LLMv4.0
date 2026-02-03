"""
Cross-Run Instability Detection (Problem 3).

Read-only diagnostic layer. No mutation of retrieval, ranking, generation, or prompts.
Strongest instability signal wins; conservative bias; reversible.
"""

from homllm.instability.interfaces import (
    InstabilityResult,
    PrimaryLabelType,
    RunRecord,
    SignalScore,
)
from homllm.instability.pipeline import run_instability

__all__ = [
    "InstabilityResult",
    "PrimaryLabelType",
    "RunRecord",
    "SignalScore",
    "run_instability",
]
