"""Confidence metrics for reranker gating."""

from __future__ import annotations

import math
from typing import Iterable

from homllm.retrieval.interfaces import Candidate


def compute_score_margin(scores: list[float]) -> float:
    """Compute top-1 vs top-2 margin."""
    if len(scores) < 2:
        return 1.0
    top1, top2 = scores[0], scores[1]
    if top1 <= 0:
        return 0.0
    return (top1 - top2) / top1


def compute_score_entropy(scores: list[float]) -> float:
    """Compute normalized entropy of score distribution."""
    if len(scores) <= 1:
        return 0.0
    total = sum(s for s in scores if s > 0)
    if total <= 0:
        return 1.0
    probs = [s / total for s in scores if s > 0]
    if len(probs) <= 1:
        return 0.0
    entropy = -sum(p * math.log(p) for p in probs)
    max_entropy = math.log(len(probs))
    return entropy / max_entropy if max_entropy > 0 else 0.0


def compute_bm25_vector_disagreement(
    candidates: Iterable[Candidate], top_k: int = 50
) -> float:
    """
    Compute disagreement between BM25 and vector rankings.

    Returns:
        Disagreement in [0, 1], where 0 means perfect agreement.
    """
    bm25_rank = _build_rank_map(
        candidates, key="bm25_score", top_k=top_k
    )
    vector_rank = _build_rank_map(
        candidates, key="vector_score", top_k=top_k
    )

    common = set(bm25_rank) & set(vector_rank)
    if len(common) < 2:
        return 0.0

    n = len(common)
    sum_sq = 0.0
    for doc_id in common:
        d = bm25_rank[doc_id] - vector_rank[doc_id]
        sum_sq += d * d

    corr = 1.0 - (6.0 * sum_sq) / (n * (n * n - 1))
    return 0.5 * (1.0 - corr)


def _build_rank_map(
    candidates: Iterable[Candidate], key: str, top_k: int
) -> dict[str, int]:
    scored = [
        (c.doc_id, getattr(c, key, 0.0))
        for c in candidates
        if getattr(c, key, 0.0) > 0
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    rank_map: dict[str, int] = {}
    for idx, (doc_id, _) in enumerate(scored[:top_k], start=1):
        rank_map[doc_id] = idx
    return rank_map


__all__ = [
    "compute_score_margin",
    "compute_score_entropy",
    "compute_bm25_vector_disagreement",
]
