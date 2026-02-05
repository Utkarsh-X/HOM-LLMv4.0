"""Diversity-aware Maximal Marginal Relevance (MMR) post-fusion.

Part of Plan B: Retrieval Layer Activation.

Implements deterministic MMR to eliminate redundancy clusters after RRF merge.
Uses cosine similarity to penalize candidates similar to already-selected items.
"""

import logging
from typing import Optional

import numpy as np

from homllm.retrieval.interfaces import Candidate

logger = logging.getLogger(__name__)


def apply_mmr(
    candidates: list[Candidate],
    embeddings: dict[str, tuple[float, ...]],
    mmr_lambda: float = 0.6,
    similarity_threshold: float = 0.85,
) -> list[Candidate]:
    """
    Apply deterministic Maximal Marginal Relevance to candidate list.
    
    Removes candidates that are too similar to already-selected items,
    breaking redundancy clusters while preserving diversity.
    
    Args:
        candidates: Sorted list of candidates (by hybrid_score descending)
        embeddings: Map of doc_id -> embedding vector
        mmr_lambda: Trade-off between relevance (1.0) and diversity (0.0)
        similarity_threshold: Max similarity to already-selected before penalty
    
    Returns:
        Re-ranked candidates with redundant items de-prioritized
    
    Invariants:
        - Deterministic: same input → same output
        - Never removes candidates, only re-ranks
        - Tie-breaker: prefer higher original rank (provenance order)
    """
    if not candidates:
        return candidates
    
    if len(candidates) <= 1:
        return candidates
    
    # If no embeddings available, return unchanged
    if not embeddings:
        logger.debug("MMR: No embeddings available, skipping")
        return candidates
    
    # Track selected candidates and their embeddings
    selected: list[Candidate] = []
    selected_embeddings: list[np.ndarray] = []
    remaining = list(candidates)
    
    # Start with the best candidate (highest hybrid_score)
    first = remaining.pop(0)
    selected.append(first)
    if first.doc_id in embeddings:
        selected_embeddings.append(np.array(embeddings[first.doc_id]))
    
    pruned_count = 0
    
    # Iteratively select candidates with MMR scoring
    while remaining:
        best_mmr_score = float('-inf')
        best_idx = 0
        best_candidate = remaining[0]
        
        for i, candidate in enumerate(remaining):
            if candidate.doc_id not in embeddings:
                # No embedding = default MMR score based on hybrid_score only
                mmr_score = candidate.hybrid_score
            else:
                candidate_emb = np.array(embeddings[candidate.doc_id])
                
                # Compute max similarity to already-selected
                max_similarity = 0.0
                if selected_embeddings:
                    for sel_emb in selected_embeddings:
                        sim = _cosine_similarity(candidate_emb, sel_emb)
                        max_similarity = max(max_similarity, sim)
                
                # Apply MMR formula: λ * relevance - (1-λ) * max_similarity
                # Relevance is the original hybrid_score (normalized)
                relevance = candidate.hybrid_score
                diversity_penalty = (1.0 - mmr_lambda) * max_similarity
                mmr_score = mmr_lambda * relevance - diversity_penalty
                
                # Log if we're about to penalize heavily
                if max_similarity > similarity_threshold:
                    logger.debug(
                        f"MMR: Penalizing {candidate.doc_id} "
                        f"(sim={max_similarity:.3f} > {similarity_threshold})"
                    )
                    pruned_count += 1
            
            # Tie-breaker: prefer earlier candidates (lower i = higher original rank)
            # We add a tiny epsilon based on original position
            mmr_score_with_tiebreak = mmr_score - (i * 1e-10)
            
            if mmr_score_with_tiebreak > best_mmr_score:
                best_mmr_score = mmr_score_with_tiebreak
                best_idx = i
                best_candidate = candidate
        
        # Move best candidate to selected
        selected.append(best_candidate)
        remaining.pop(best_idx)
        
        if best_candidate.doc_id in embeddings:
            selected_embeddings.append(np.array(embeddings[best_candidate.doc_id]))
    
    if pruned_count > 0:
        logger.info(f"MMR: De-prioritized {pruned_count} similar candidates")
    
    return selected


def compute_candidate_embeddings(
    candidates: list[Candidate],
    embedder: object,
) -> dict[str, tuple[float, ...]]:
    """
    Compute embeddings for candidate content.
    
    Args:
        candidates: List of candidates
        embedder: Embedder with embed_code() method
    
    Returns:
        Map of doc_id -> embedding vector
    """
    embeddings: dict[str, tuple[float, ...]] = {}
    
    for candidate in candidates:
        if not candidate.content:
            continue
        
        try:
            # Use embed_code for code content
            vector = embedder.embed_code(candidate.content)
            embeddings[candidate.doc_id] = vector.values
        except Exception as e:
            logger.debug(f"Failed to embed {candidate.doc_id}: {e}")
            continue
    
    return embeddings


def _cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    try:
        # Normalize vectors
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 < 1e-8 or norm2 < 1e-8:
            return 0.0
        
        v1_norm = vec1 / norm1
        v2_norm = vec2 / norm2
        
        return float(np.dot(v1_norm, v2_norm))
    except Exception:
        return 0.0
