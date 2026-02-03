"""
Intent-Gated Sufficiency Layer (plan §1–§7).

Read-only diagnostic: measures whether retrieved context is sufficient for the query,
emits machine-readable verdict and attribution. Does not influence generation,
retrieval, ranking, or prompts.
"""

from homllm.sufficiency.interfaces import (
    IntentResult,
    SignalResult,
    SufficiencyResult,
)
from homllm.sufficiency.pipeline import run_sufficiency

__all__ = [
    "run_sufficiency",
    "IntentResult",
    "SignalResult",
    "SufficiencyResult",
]
