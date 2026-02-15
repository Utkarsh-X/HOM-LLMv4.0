"""Query preparer implementation."""

import re
from typing import Optional

from homllm.common.types import Intent
from homllm.retrieval.interfaces import PreparedQuery, QueryPreparer, RetrievalConfig
from homllm.retrieval.query_expansion import DeterministicQueryExpander


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

        return PreparedQuery(
            dense_query=query,
            lexical_terms=expanded_terms,
            intent=intent,
            lexical_expansion_terms=expansion_terms,
        )
