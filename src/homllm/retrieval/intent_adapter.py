"""Conservative query-to-intent adapter for retrieval."""

from __future__ import annotations

from dataclasses import dataclass
import re

from homllm.common.types import Intent


@dataclass(frozen=True)
class IntentInference:
    intent: Intent
    source: str
    matched_rule: str


_REFACTOR_PATTERNS = (
    r"\brefactor\b",
    r"\brestructure\b",
    r"\brename\b",
    r"\bextract\b",
    r"\bclean\s*up\b",
)

_IMPLEMENT_PATTERNS = (
    r"\bimplement\b",
    r"\badd\b",
    r"\bbuild\b",
    r"\bcreate\b",
    r"\bwrite\b",
    r"\bdesign\b",
    r"\bhow\s+should\b",
    r"\bwhat\s+should\b",
)

_SEARCH_PATTERNS = (
    r"\bcompare\b",
    r"\bversus\b",
    r"\bvs\.?\b",
    r"\bdifference(?:s)?\b",
    r"\bwhere\s+is\b",
    r"\bwhere\s+are\b",
    r"\blocate\b",
    r"\bfind\b",
    r"\bwhich\s+file\b",
)

_DEBUG_PATTERNS = (
    r"\bwhy\s+does\b",
    r"\bwhat\s+causes\b",
    r"\bdebug\b",
    r"\berror\b",
    r"\bexception\b",
    r"\bbug\b",
    r"\bfail(?:s|ed|ure)?\b",
    r"\bmissing\b",
    r"\bmismatch(?:ed)?\b",
    r"\btimeout\b",
    r"\btime\s*out\b",
    r"\bnan\b",
    r"\binvalid\b",
)

_EXPLAIN_PATTERNS = (
    r"\bhow\b",
    r"\bwhat\b",
    r"\bwhy\b",
    r"\bdescribe\b",
    r"\btrace\b",
    r"\bsummarize\b",
    r"\blifecycle\b",
    r"\bflow\b",
    r"\bsequence\b",
)


def infer_retrieval_intent(query: str) -> IntentInference:
    """Infer a conservative retrieval intent for activating retrieval features."""
    q = (query or "").strip().lower()
    if not q:
        return IntentInference(Intent.UNKNOWN, "fallback", "empty_query")

    for pattern in _REFACTOR_PATTERNS:
        if re.search(pattern, q):
            return IntentInference(Intent.REFACTOR, "heuristic", pattern)

    for pattern in _IMPLEMENT_PATTERNS:
        if re.search(pattern, q):
            return IntentInference(Intent.IMPLEMENT, "heuristic", pattern)

    for pattern in _SEARCH_PATTERNS:
        if re.search(pattern, q):
            return IntentInference(Intent.SEARCH, "heuristic", pattern)

    for pattern in _DEBUG_PATTERNS:
        if re.search(pattern, q):
            return IntentInference(Intent.DEBUG, "heuristic", pattern)

    for pattern in _EXPLAIN_PATTERNS:
        if re.search(pattern, q):
            return IntentInference(Intent.EXPLAIN, "heuristic", pattern)

    return IntentInference(Intent.UNKNOWN, "fallback", "no_match")
