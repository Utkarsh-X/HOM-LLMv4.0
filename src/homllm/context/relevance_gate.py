"""Tier 3B Section 4: Lightweight Relevance Safety Guard.

Prevents generation on irrelevant context by checking cosine similarity
between query embedding and top-K ranked blocks.

If max similarity < threshold, the gate triggers and returns
a "No relevant context found" response instead of generating from
structurally good but semantically irrelevant context.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RelevanceGateResult:
    """Result of the relevance gate check."""

    triggered: bool
    max_similarity: float
    top_k_similarities: list[float]


def relevance_gate(
    query_embedding: list[float] | None,
    block_embeddings: list[list[float] | None],
    threshold: float = 0.25,
    top_k: int = 5,
) -> RelevanceGateResult:
    """Check if top-K blocks are relevant to the query.

    Uses cosine similarity between query embedding and block embeddings.
    If max similarity across top-K blocks is below threshold, the gate
    triggers (context is likely irrelevant).

    Args:
        query_embedding: Query embedding vector (or None if unavailable).
        block_embeddings: Embeddings for the top blocks.
        threshold: Minimum similarity to pass the gate.
        top_k: Number of top blocks to check.

    Returns:
        RelevanceGateResult with trigger status and scores.
    """
    # If no embeddings available, pass the gate (don't block)
    if query_embedding is None or not block_embeddings:
        return RelevanceGateResult(
            triggered=False,
            max_similarity=1.0,
            top_k_similarities=[],
        )

    # Take top-K block embeddings
    check_embeddings = block_embeddings[:top_k]

    similarities = []
    for emb in check_embeddings:
        if emb is None:
            continue
        sim = _cosine_similarity(query_embedding, emb)
        similarities.append(sim)

    if not similarities:
        return RelevanceGateResult(
            triggered=False,
            max_similarity=1.0,
            top_k_similarities=[],
        )

    max_sim = max(similarities)
    triggered = max_sim < threshold

    if triggered:
        logger.warning(
            "[RELEVANCE_GATE] Triggered: max_sim=%.3f < threshold=%.3f, "
            "top_%d sims=%s",
            max_sim,
            threshold,
            top_k,
            [round(s, 3) for s in similarities],
        )
    else:
        logger.info(
            "[RELEVANCE_GATE] Passed: max_sim=%.3f >= threshold=%.3f",
            max_sim,
            threshold,
        )

    return RelevanceGateResult(
        triggered=triggered,
        max_similarity=round(max_sim, 4),
        top_k_similarities=[round(s, 4) for s in similarities],
    )


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5

    if norm_a < 1e-10 or norm_b < 1e-10:
        return 0.0

    return dot / (norm_a * norm_b)
