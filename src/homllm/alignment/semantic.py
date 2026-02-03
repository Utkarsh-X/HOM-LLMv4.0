"""
Semantic Alignment Computation - QCSA

Query–Context Semantic Alignment signal computation.
Uses embedding cosine similarity to measure semantic alignment
between query and context blocks.

CONSTRAINTS:
- Read-only, deterministic
- No thresholds for decisions
- Raw numeric values only
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact
    from homllm.indexer.embedder import QwenEmbedder

from .interfaces import SemanticAlignment


def _cosine_similarity(vec1: tuple[float, ...], vec2: tuple[float, ...]) -> float:
    """
    Compute cosine similarity between two vectors.
    
    Returns value in range [-1, 1], where 1 = identical direction.
    """
    if len(vec1) != len(vec2) or len(vec1) == 0:
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


def compute_semantic_alignment(
    query: str,
    context_artifact: "ContextArtifact",
    embedder: "QwenEmbedder",
) -> SemanticAlignment:
    """
    Compute Query–Context Semantic Alignment signals.
    
    Args:
        query: The user query string
        context_artifact: Assembled context with blocks
        embedder: Embedding model for computing vectors
        
    Returns:
        SemanticAlignment with raw numeric signals
        
    GUARANTEES:
    - Deterministic (same input → same output)
    - No side effects
    - No threshold-based decisions
    """
    if not context_artifact.blocks:
        return SemanticAlignment.empty()
    
    # Embed the query
    query_vector = embedder.embed_query(query)
    query_values = query_vector.values
    
    # Embed each context block and compute similarities
    similarities: list[float] = []
    
    for block in context_artifact.blocks:
        block_vector = embedder.embed_code(block.content)
        block_values = block_vector.values
        
        similarity = _cosine_similarity(query_values, block_values)
        similarities.append(similarity)
    
    if not similarities:
        return SemanticAlignment.empty()
    
    # Compute statistics
    n = len(similarities)
    mean_sim = sum(similarities) / n
    min_sim = min(similarities)
    max_sim = max(similarities)
    
    # Variance computation
    if n > 1:
        variance = sum((s - mean_sim) ** 2 for s in similarities) / n
    else:
        variance = 0.0
    
    # Outlier detection: blocks > 2 standard deviations from mean
    std_dev = math.sqrt(variance) if variance > 0 else 0.0
    outlier_threshold = 2 * std_dev
    outlier_count = sum(
        1 for s in similarities 
        if abs(s - mean_sim) > outlier_threshold
    ) if std_dev > 0 else 0
    
    return SemanticAlignment(
        mean_similarity=mean_sim,
        min_similarity=min_sim,
        max_similarity=max_sim,
        similarity_variance=variance,
        outlier_block_count=outlier_count,
        block_similarities=tuple(similarities),
    )


__all__ = ["compute_semantic_alignment"]
