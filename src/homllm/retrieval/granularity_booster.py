"""Intent-driven granularity boosting.

Part of Plan B: Retrieval Layer Activation.

Applies multiplicative score boosts based on query intent and chunk granularity.
Skips silently if chunk metadata is missing (backward-compatible).
"""

import logging
from typing import Optional

from homllm.common.types import Intent
from homllm.retrieval.interfaces import Candidate

logger = logging.getLogger(__name__)


# Default boost table following Plan B spec
# Keys match Intent enum values: EXPLAIN, IMPLEMENT, REFACTOR, DEBUG, SEARCH, UNKNOWN
DEFAULT_GRANULARITY_BOOST_TABLE: dict[str, dict[str, float]] = {
    "EXPLAIN": {
        "coarse": 1.5,
        "medium": 1.5,
        "fine": 1.0,
    },
    "IMPLEMENT": {
        "fine": 2.0,
        "medium": 1.2,
        "coarse": 0.8,
    },
    "REFACTOR": {
        "fine": 1.8,
        "medium": 1.5,
        "coarse": 1.0,
    },
    "DEBUG": {
        "fine": 2.5,
        "medium": 1.5,
        "coarse": 1.0,
    },
    "SEARCH": {
        "medium": 1.8,
        "fine": 1.5,
        "coarse": 1.0,
    },
    # Default for unknown intents
    "UNKNOWN": {
        "fine": 1.0,
        "medium": 1.0,
        "coarse": 1.0,
    },
}


def apply_granularity_boost(
    candidates: list[Candidate],
    intent: Intent,
    boost_table: Optional[dict[str, dict[str, float]]] = None,
    granularity_lookup: Optional[dict[str, str]] = None,
) -> list[Candidate]:
    """
    Apply multiplicative granularity boost to candidates based on intent.
    
    Args:
        candidates: List of candidates to boost
        intent: Query intent (EXPLANATORY, IMPLEMENTATION, FACTUAL, DEBUG, UNKNOWN)
        boost_table: Custom boost table (defaults to DEFAULT_GRANULARITY_BOOST_TABLE)
        granularity_lookup: Map of doc_id -> granularity_level (from chunk table)
    
    Returns:
        Candidates with adjusted hybrid_scores (re-sorted)
    
    Invariants:
        - Deterministic: same input → same output
        - Skips silently if granularity metadata missing
        - Never modifies original candidates (creates new)
    """
    if not candidates:
        return candidates
    
    table = boost_table or DEFAULT_GRANULARITY_BOOST_TABLE
    intent_key = intent.value.upper() if hasattr(intent, 'value') else str(intent).upper()
    
    # Get boost map for this intent
    intent_boosts = table.get(intent_key, table.get("UNKNOWN", {}))
    
    if not intent_boosts:
        logger.debug(f"Granularity boost: No boosts for intent {intent_key}")
        return candidates
    
    boosted: list[Candidate] = []
    boost_count = 0
    
    for candidate in candidates:
        # Try to get granularity from lookup or candidate metadata
        granularity = None
        
        if granularity_lookup and candidate.doc_id in granularity_lookup:
            granularity = granularity_lookup[candidate.doc_id]
        
        # If no granularity, skip silently
        if not granularity:
            boosted.append(candidate)
            continue
        
        # Get boost multiplier
        boost = intent_boosts.get(granularity.lower(), 1.0)
        
        if boost != 1.0:
            # Apply multiplicative boost
            new_score = candidate.hybrid_score * boost
            boosted_candidate = Candidate(
                doc_id=candidate.doc_id,
                file=candidate.file,
                symbol_id=candidate.symbol_id,
                content=candidate.content,
                bm25_score=candidate.bm25_score,
                vector_score=candidate.vector_score,
                hybrid_score=new_score,
                provenance=candidate.provenance + (f"granularity_boost:{granularity}:{boost}",),
                granularity_level=granularity,
                span_start=candidate.span_start,
                span_end=candidate.span_end,
                parent_symbol_id=candidate.parent_symbol_id,
                entity_ids=candidate.entity_ids,
                doc_type=candidate.doc_type,
                semantic_embedding=candidate.semantic_embedding,
                symbol_name=candidate.symbol_name,
            )
            boosted.append(boosted_candidate)
            boost_count += 1
            logger.debug(
                f"Granularity boost: {candidate.doc_id} "
                f"{granularity} x{boost} → {new_score:.4f}"
            )
        else:
            # No boost, just add granularity level
            boosted.append(Candidate(
                doc_id=candidate.doc_id,
                file=candidate.file,
                symbol_id=candidate.symbol_id,
                content=candidate.content,
                bm25_score=candidate.bm25_score,
                vector_score=candidate.vector_score,
                hybrid_score=candidate.hybrid_score,
                provenance=candidate.provenance,
                granularity_level=granularity,
                span_start=candidate.span_start,
                span_end=candidate.span_end,
                parent_symbol_id=candidate.parent_symbol_id,
                entity_ids=candidate.entity_ids,
                doc_type=candidate.doc_type,
                semantic_embedding=candidate.semantic_embedding,
                symbol_name=candidate.symbol_name,
            ))
    
    if boost_count > 0:
        logger.info(f"Granularity boost: Applied to {boost_count} candidates for intent {intent_key}")
    
    # Re-sort by hybrid_score descending
    boosted.sort(key=lambda c: c.hybrid_score, reverse=True)
    
    return boosted


def build_granularity_lookup(
    duckdb_adapter: object,
    candidate_doc_ids: list[str],
) -> dict[str, str]:
    """
    Build granularity lookup from chunks table.
    
    Args:
        duckdb_adapter: DuckDB adapter with get_chunk_granularity method
        candidate_doc_ids: List of doc_ids to look up
    
    Returns:
        Map of doc_id -> granularity_level
    """
    lookup: dict[str, str] = {}
    
    if not hasattr(duckdb_adapter, 'get_chunk_granularity'):
        return lookup
    
    for doc_id in candidate_doc_ids:
        try:
            granularity = duckdb_adapter.get_chunk_granularity(doc_id)
            if granularity:
                lookup[doc_id] = granularity
        except Exception as e:
            logger.debug(f"Failed to get granularity for {doc_id}: {e}")
            continue
    
    return lookup
