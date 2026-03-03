"""Query preparer implementation."""

import re
from typing import Optional

from homllm.common.types import Intent
from homllm.retrieval.interfaces import PreparedQuery, QueryPreparer, RetrievalConfig
from homllm.retrieval.query_expansion import DeterministicQueryExpander

_HIGH_COMPLEXITY_PATTERNS = (
    r"\btrace\b",
    r"\bflow\b",
    r"\bacross\b",
    r"\bend[-\s]*to[-\s]*end\b",
    r"\bchain\b",
    r"\bsequence\b",
    r"\bpipeline\b",
    r"\bmulti[-\s]*hop\b",
    r"\ball\s+\d+\b",
)
_MEDIUM_COMPLEXITY_PATTERNS = (
    r"\ball\b",
    r"\bcompare\b",
    r"\bbetween\b",
    r"\bwhen\b",
    r"\bhow\s+do(?:es)?\b",
    r"\bcombine\b",
)
_NAMED_COMPONENT_PATTERN = re.compile(
    r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b|\b[a-z]+_[a-z]+\b|\b[A-Z]+_[A-Z0-9_]+\b|\bL\d+\b"
)


def estimate_required_k(query: str) -> int:
    """
    Lightweight query complexity classifier (A4).
    Returns estimated retrieval k: 50 (standard), 65 (medium), or 80 (synthesis).
    """
    query_lower = query.lower()

    # Count distinct named components to avoid over-classifying repeated mentions.
    named_components = len({m.lower() for m in _NAMED_COMPONENT_PATTERN.findall(query)})

    # Use bounded regex patterns (not raw substring checks) to avoid false positives
    # like matching "all" inside "fallback".
    high_complexity_score = sum(
        1 for pattern in _HIGH_COMPLEXITY_PATTERNS if re.search(pattern, query_lower)
    )
    medium_complexity_score = sum(
        1 for pattern in _MEDIUM_COMPLEXITY_PATTERNS if re.search(pattern, query_lower)
    )

    if (
        named_components >= 3
        or high_complexity_score >= 2
        or (high_complexity_score >= 1 and medium_complexity_score >= 1)
    ):
        return 80
    if (
        high_complexity_score >= 1
        or medium_complexity_score >= 2
        or named_components >= 2
    ):
        return 65
    return 50


class SimpleQueryPreparer(QueryPreparer):
    """Simple query preparer without LLM rewriting."""

    def __init__(self, config: Optional[RetrievalConfig] = None):
        if config is None:
            self._expander = DeterministicQueryExpander(
                enabled=False,
                max_terms=0,
                min_token_length=3,
                synonyms={},
            )
            return

        self._expander = DeterministicQueryExpander(
            enabled=config.query_expansion_enabled,
            max_terms=config.query_expansion_max_terms,
            min_token_length=config.query_expansion_min_token_length,
            synonyms=config.query_expansion_synonyms,
        )

    def prepare(self, query: str, intent: Intent) -> PreparedQuery:
        """
        Returns:
            dense_query: Raw query text for embedding
            lexical_terms: Extracted keywords for BM25
        
        FORBIDDEN: Modifying query based on repo-specific patterns.
        """
        # Extract keywords (simple tokenization)
        # Remove common stop words and punctuation
        words = re.findall(r"\b\w+\b", query.lower())
        stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"}
        lexical_terms = [w for w in words if w not in stop_words and len(w) > 2]
        expanded_terms, expansion_terms = self._expander.expand(lexical_terms)
        required_k = estimate_required_k(query)

        return PreparedQuery(
            dense_query=query,
            lexical_terms=expanded_terms,
            intent=intent,
            lexical_expansion_terms=expansion_terms,
            required_k=required_k,
        )
