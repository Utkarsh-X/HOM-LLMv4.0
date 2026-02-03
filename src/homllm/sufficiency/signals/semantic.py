"""
Semantic Coverage Signal (plan §5.2).

Query vs context centroid similarity + diversity of context embeddings.
Deterministic. Frozen encoder only (no LLM). Never authoritative alone (soft veto).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from homllm.sufficiency.interfaces import LabelType, SignalResult

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact
    from homllm.indexer.embedder import QwenEmbedder


def _cosine_sim(vec1: tuple[float, ...], vec2: tuple[float, ...]) -> float:
    if len(vec1) != len(vec2) or len(vec1) == 0:
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    n1 = math.sqrt(sum(a * a for a in vec1))
    n2 = math.sqrt(sum(b * b for b in vec2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (n1 * n2)))


def compute_semantic_signal(
    query: str,
    context_artifact: "ContextArtifact",
    embedder: "QwenEmbedder | None",
) -> SignalResult:
    """
    Semantic coverage: query–centroid similarity and diversity.
    If embedder is None, returns conservative INSUFFICIENT (score 0.0).
    """
    if embedder is None or not context_artifact.blocks:
        return SignalResult(score=0.0, label="INSUFFICIENT")

    query_vec = embedder.embed_query(query).values
    dim = len(query_vec)
    if dim == 0:
        return SignalResult(score=0.0, label="INSUFFICIENT")

    # Block embeddings and centroid
    block_vectors: list[tuple[float, ...]] = []
    for block in context_artifact.blocks:
        v = embedder.embed_code(block.content).values
        if len(v) == dim:
            block_vectors.append(v)

    if not block_vectors:
        return SignalResult(score=0.0, label="INSUFFICIENT")

    centroid = tuple(
        sum(block_vectors[i][d] for i in range(len(block_vectors))) / len(block_vectors)
        for d in range(dim)
    )
    centroid_sim = _cosine_sim(query_vec, centroid)

    # Diversity: mean pairwise distance (higher spread → higher diversity)
    n = len(block_vectors)
    if n == 1:
        diversity = 0.0
    else:
        pair_dists = []
        for i in range(n):
            for j in range(i + 1, n):
                sim = _cosine_sim(block_vectors[i], block_vectors[j])
                pair_dists.append(1.0 - sim)
        diversity = sum(pair_dists) / len(pair_dists) if pair_dists else 0.0

    # Score: centroid similarity weighted with diversity (0..1)
    # Plan: "semantic alignment" + "diversity". Combine: 0.7 * sim + 0.3 * diversity
    sim_norm = (centroid_sim + 1.0) / 2.0  # [0, 1]
    score = 0.7 * sim_norm + 0.3 * min(1.0, diversity)
    score = max(0.0, min(1.0, score))

    # Deterministic threshold (no learning)
    label: LabelType = "SUFFICIENT" if score >= 0.5 else "INSUFFICIENT"
    return SignalResult(score=score, label=label)
