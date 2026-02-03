"""
Structural Explanation Gap Detection (Problem 4).

Read-only diagnostic. Advisory guidance only. No generation, retrieval, or prompt mutation.
Escalation only upward; conservative bias; rules dominate classifiers.
"""

from homllm.explanation_gap.interfaces import (
    DepthIntentType,
    DepthLabelType,
    ExplanationGapResult,
    HistoryDepthStats,
    SignalOutput,
)
from homllm.explanation_gap.pipeline import (
    run_explanation_gap,
    run_explanation_gap_with_embedder,
)

__all__ = [
    "DepthIntentType",
    "DepthLabelType",
    "ExplanationGapResult",
    "HistoryDepthStats",
    "SignalOutput",
    "run_explanation_gap",
    "run_explanation_gap_with_embedder",
]
