"""
Query Intent Classifier (non-LLM).

Rule-based keyword patterns to select mandatory sufficiency axes.
No LLM calls. Deterministic. Conservative default (UNKNOWN → all axes mandatory).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from homllm.sufficiency.interfaces import (
    AxisType,
    IntentResult,
    IntentType,
)

if TYPE_CHECKING:
    pass


# Keyword patterns per intent (deterministic, no learning)
_ARCHITECTURAL_PATTERNS = re.compile(
    r"\b(how\s+do(es)?\s+.*\s+combine|all\s+\d+\s+rules?|lifecycle|execution\s+flow|"
    r"trace\s+.*\s+flow|layers?|priority\s+order|conflict(s)?\s+between|"
    r"optimization\s+rules?|plan\s+caching|execution\s+timing)\b",
    re.IGNORECASE,
)
_IMPLEMENTATION_PATTERNS = re.compile(
    r"\b(how\s+does\s+\w+\s+work|what\s+happens\s+when|method|function|"
    r"implement|resolve|handle\s+partial|at-least-once|semantics?)\b",
    re.IGNORECASE,
)
_BEHAVIORAL_PATTERNS = re.compile(
    r"\b(behave|behavior|when\s+all\s+connections?\s+(are\s+)?in\s+use|"
    r"wait\s+or\s+time\s+out|time\s+out|callers?\s+wait)\b",
    re.IGNORECASE,
)


def classify_intent(query: str) -> IntentResult:
    """
    Classify query intent using rule-based keyword patterns only.
    No LLM. No embedding. Deterministic.

    Mandatory axes per intent (plan §5.1, §6.1):
    - ARCHITECTURAL: STRUCTURAL, SEMANTIC. early_exit_allowed = False.
    - IMPLEMENTATION: RULE, STRUCTURAL, SEMANTIC.
    - BEHAVIORAL: RULE, SEMANTIC.
    - UNKNOWN: all three (conservative).
    """
    q = query.strip()
    if not q:
        return _unknown_intent()

    if _ARCHITECTURAL_PATTERNS.search(q):
        return IntentResult(
            intent="ARCHITECTURAL",
            mandatory_axes=("STRUCTURAL", "SEMANTIC"),
            early_exit_allowed=False,
        )
    if _BEHAVIORAL_PATTERNS.search(q):
        return IntentResult(
            intent="BEHAVIORAL",
            mandatory_axes=("RULE", "SEMANTIC"),
            early_exit_allowed=True,
        )
    if _IMPLEMENTATION_PATTERNS.search(q):
        return IntentResult(
            intent="IMPLEMENTATION",
            mandatory_axes=("RULE", "STRUCTURAL", "SEMANTIC"),
            early_exit_allowed=True,
        )

    return _unknown_intent()


def _unknown_intent() -> IntentResult:
    """Conservative default: all axes mandatory."""
    return IntentResult(
        intent="UNKNOWN",
        mandatory_axes=("STRUCTURAL", "RULE", "SEMANTIC"),
        early_exit_allowed=False,
    )


__all__ = ["classify_intent"]
