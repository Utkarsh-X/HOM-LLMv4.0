"""Signal profile computation for adaptive ranking."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from homllm.retrieval.interfaces import Candidate


@dataclass(frozen=True)
class SignalProfile:
    """Observed retrieval landscape metrics."""

    margin: float
    score_entropy: float
    score_variance: float
    bm25_vector_correlation: float
    file_entropy: float
    granularity_entropy: float
    unique_files: int
    avg_graph_distance: float
    is_confident: bool
    is_dispersed: bool
    is_structural: bool


def compute_signal_profile(
    candidates: Iterable[Candidate],
    scores: dict[str, float],
    distance_map: dict[str, int] | None,
) -> SignalProfile:
    candidates_list = list(candidates)
    ordered_scores = sorted(
        (scores.get(c.doc_id, 0.0) for c in candidates_list), reverse=True
    )
    margin = _compute_margin(ordered_scores)
    score_entropy = _compute_entropy(ordered_scores)
    score_variance = _compute_variance(ordered_scores)
    bm25_vector_correlation = _compute_bm25_vector_corr(candidates_list)

    file_entropy, unique_files = _compute_file_entropy(candidates_list)
    granularity_entropy = _compute_granularity_entropy(candidates_list)
    avg_graph_distance = _compute_avg_graph_distance(
        candidates_list, distance_map or {}
    )

    is_confident = margin > 0.3
    is_dispersed = file_entropy > 0.6
    is_structural = avg_graph_distance < 2.0 if avg_graph_distance >= 0 else False

    return SignalProfile(
        margin=margin,
        score_entropy=score_entropy,
        score_variance=score_variance,
        bm25_vector_correlation=bm25_vector_correlation,
        file_entropy=file_entropy,
        granularity_entropy=granularity_entropy,
        unique_files=unique_files,
        avg_graph_distance=avg_graph_distance,
        is_confident=is_confident,
        is_dispersed=is_dispersed,
        is_structural=is_structural,
    )


def _compute_margin(scores: list[float]) -> float:
    if len(scores) < 2:
        return 1.0
    top1, top2 = scores[0], scores[1]
    if top1 <= 0:
        return 0.0
    return (top1 - top2) / top1


def _compute_entropy(scores: list[float]) -> float:
    total = sum(s for s in scores if s > 0)
    if total <= 0:
        return 1.0
    probs = [s / total for s in scores if s > 0]
    if len(probs) <= 1:
        return 0.0
    entropy = -sum(p * math.log(p) for p in probs)
    max_entropy = math.log(len(probs))
    return entropy / max_entropy if max_entropy > 0 else 0.0


def _compute_variance(scores: list[float]) -> float:
    if not scores:
        return 0.0
    mean = sum(scores) / len(scores)
    return sum((s - mean) ** 2 for s in scores) / len(scores)


def _compute_bm25_vector_corr(candidates: list[Candidate]) -> float:
    bm25_rank = _build_rank_map(candidates, key="bm25_score")
    vector_rank = _build_rank_map(candidates, key="vector_score")
    common = set(bm25_rank) & set(vector_rank)
    if len(common) < 2:
        return 0.0
    n = len(common)
    sum_sq = 0.0
    for doc_id in common:
        d = bm25_rank[doc_id] - vector_rank[doc_id]
        sum_sq += d * d
    return 1.0 - (6.0 * sum_sq) / (n * (n * n - 1))


def _build_rank_map(
    candidates: list[Candidate], key: str, top_k: int = 50
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


def _compute_file_entropy(
    candidates: list[Candidate],
) -> tuple[float, int]:
    files = [c.file for c in candidates if c.file]
    unique_files = len(set(files))
    if unique_files <= 1:
        return 0.0, unique_files
    counts: dict[str, int] = {}
    for f in files:
        counts[f] = counts.get(f, 0) + 1
    total = sum(counts.values())
    probs = [count / total for count in counts.values()]
    entropy = -sum(p * math.log(p) for p in probs)
    max_entropy = math.log(unique_files)
    return entropy / max_entropy if max_entropy > 0 else 0.0, unique_files


def _compute_granularity_entropy(candidates: list[Candidate]) -> float:
    levels = [(c.granularity_level or "unknown").lower() for c in candidates]
    unique_levels = len(set(levels))
    if unique_levels <= 1:
        return 0.0
    counts: dict[str, int] = {}
    for level in levels:
        counts[level] = counts.get(level, 0) + 1
    total = sum(counts.values())
    probs = [count / total for count in counts.values()]
    entropy = -sum(p * math.log(p) for p in probs)
    max_entropy = math.log(unique_levels)
    return entropy / max_entropy if max_entropy > 0 else 0.0


def _compute_avg_graph_distance(
    candidates: list[Candidate], distance_map: dict[str, int]
) -> float:
    distances: list[int] = []
    for c in candidates:
        if c.symbol_id and c.symbol_id in distance_map:
            distances.append(distance_map[c.symbol_id])
    if not distances:
        return -1.0
    return sum(distances) / len(distances)


__all__ = ["SignalProfile", "compute_signal_profile"]
