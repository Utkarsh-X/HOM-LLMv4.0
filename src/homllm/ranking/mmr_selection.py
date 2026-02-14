"""MMR selection for diversity-aware ranking output."""

from __future__ import annotations

from typing import Iterable

from homllm.retrieval.interfaces import Candidate


def select_mmr(
    candidates: list[Candidate],
    max_items: int,
    lambda_value: float,
    relevance_map: dict[str, float] | None = None,
) -> list[Candidate]:
    if not candidates or max_items <= 0:
        return []

    selected: list[Candidate] = []
    remaining = list(candidates)

    while remaining and len(selected) < max_items:
        best_score = None
        best_idx = None

        for idx, candidate in enumerate(remaining):
            relevance = _safe_score(candidate, relevance_map)
            similarity = _max_similarity(candidate, selected)
            mmr_score = lambda_value * relevance - (1.0 - lambda_value) * similarity

            if best_score is None or mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx

        if best_idx is None:
            break

        selected.append(remaining.pop(best_idx))

    return selected


def _safe_score(
    candidate: Candidate, relevance_map: dict[str, float] | None
) -> float:
    if relevance_map is not None:
        return relevance_map.get(candidate.doc_id, 0.0)
    return getattr(candidate, "hybrid_score", 0.0)


def _max_similarity(candidate: Candidate, selected: Iterable[Candidate]) -> float:
    max_sim = 0.0
    for other in selected:
        max_sim = max(max_sim, _similarity(candidate, other))
    return max_sim


def _similarity(a: Candidate, b: Candidate) -> float:
    # Prefer overlap-based similarity; same-file alone should not be penalized.
    span_overlap = _span_overlap_ratio(a, b)
    return span_overlap


def _span_overlap_ratio(a: Candidate, b: Candidate) -> float:
    if a.span_start is None or a.span_end is None:
        return 0.0
    if b.span_start is None or b.span_end is None:
        return 0.0
    if a.file != b.file:
        return 0.0

    start = max(a.span_start, b.span_start)
    end = min(a.span_end, b.span_end)
    if start > end:
        return 0.0

    overlap = end - start + 1
    length = max(a.span_end - a.span_start + 1, b.span_end - b.span_start + 1)
    return overlap / length if length > 0 else 0.0


__all__ = ["select_mmr"]
