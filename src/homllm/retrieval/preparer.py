"""Query preparer implementation."""

import re
from typing import Optional

from homllm.common.types import Intent
from homllm.retrieval.interfaces import PreparedQuery, QueryPreparer


class SimpleQueryPreparer(QueryPreparer):
    """Simple query preparer without LLM rewriting."""

    def prepare(self, query: str, intent: Intent) -> PreparedQuery:
        """
        Returns:
            dense_query: Instruction-wrapped query for embedding
            lexical_terms: Extracted keywords for BM25
        
        FORBIDDEN: Modifying query based on repo-specific patterns.
        """
        # Extract keywords (simple tokenization)
        # Remove common stop words and punctuation
        words = re.findall(r"\b\w+\b", query.lower())
        stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"}
        lexical_terms = [w for w in words if w not in stop_words and len(w) > 2]

        # Create instruction-wrapped query for embedding
        dense_query = f"Represent this code search query for retrieval: {query}"

        return PreparedQuery(
            dense_query=dense_query,
            lexical_terms=lexical_terms,
            intent=intent,
        )
