"""
Rule / Entity Coverage Signal (plan §5.3).

Query term extraction and n-gram/identifier overlap with context.
Deterministic. No LLM. Hard veto when mandatory and failed.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from homllm.sufficiency.interfaces import LabelType, SignalResult

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact


# Extract identifiers and important terms from query (deterministic)
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
# Skip very common words that don't indicate entity coverage
_STOP = frozenset(
    {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
     "have", "has", "had", "do", "does", "did", "will", "would", "could",
     "should", "may", "might", "must", "shall", "can", "need", "dare",
     "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
     "into", "through", "during", "before", "after", "above", "below",
     "how", "what", "when", "where", "which", "who", "and", "or", "but"}
)


def compute_rule_signal(
    query: str,
    context_artifact: "ContextArtifact",
) -> SignalResult:
    """
    Rule/entity coverage: overlap of query terms (identifiers, n-grams) with context.
    Deterministic. No embedding.
    """
    if not context_artifact.blocks:
        return SignalResult(score=0.0, label="INSUFFICIENT")

    query_terms = set(
        m.group(0) for m in _IDENTIFIER_RE.finditer(query)
        if m.group(0).lower() not in _STOP and len(m.group(0)) > 1
    )
    if not query_terms:
        # No meaningful terms → conservatively insufficient for rule axis
        return SignalResult(score=0.0, label="INSUFFICIENT")

    context_text = " ".join(b.content for b in context_artifact.blocks)
    context_lower = context_text.lower()
    matched = sum(1 for t in query_terms if t.lower() in context_lower or t in context_text)
    score = matched / len(query_terms)
    score = max(0.0, min(1.0, score))

    # Deterministic threshold
    label: LabelType = "SUFFICIENT" if score >= 0.3 else "INSUFFICIENT"
    return SignalResult(score=score, label=label)
