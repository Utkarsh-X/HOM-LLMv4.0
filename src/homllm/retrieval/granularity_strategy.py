"""Granularity-aware candidate mixing strategy."""

from __future__ import annotations

from homllm.common.types import Intent
from homllm.retrieval.interfaces import Candidate


_MIX_BY_INTENT: dict[str, dict[str, tuple[int, int]]] = {
    "explain": {"fine": (3, 8), "medium": (2, 6), "coarse": (1, 4)},
    "implement": {"fine": (8, 15), "medium": (1, 4), "coarse": (0, 1)},
    "debug": {"fine": (10, 18), "medium": (1, 3), "coarse": (0, 1)},
    "search": {"fine": (2, 5), "medium": (3, 8), "coarse": (2, 5)},
    "refactor": {"fine": (6, 12), "medium": (2, 5), "coarse": (1, 2)},
    "unknown": {"fine": (5, 10), "medium": (2, 5), "coarse": (1, 2)},
}


def apply_granularity_mix(
    candidates: list[Candidate],
    intent: Intent,
) -> list[Candidate]:
    """Ensure retrieval set contains a useful mix of granularities."""
    if not candidates:
        return candidates

    intent_key = str(intent.value if isinstance(intent, Intent) else intent).lower()
    constraints = _MIX_BY_INTENT.get(intent_key, _MIX_BY_INTENT["unknown"])

    ranked = sorted(candidates, key=lambda c: c.hybrid_score, reverse=True)
    buckets: dict[str, list[Candidate]] = {"fine": [], "medium": [], "coarse": [], "unknown": []}
    for candidate in ranked:
        level = (candidate.granularity_level or "unknown").lower()
        buckets[level if level in buckets else "unknown"].append(candidate)

    selected_ids: set[str] = set()
    selected: list[Candidate] = []

    for level, (minimum, maximum) in constraints.items():
        bucket = buckets.get(level, [])
        if not bucket:
            continue
        take = min(maximum, len(bucket))
        for candidate in bucket[:take]:
            if candidate.doc_id not in selected_ids:
                selected.append(candidate)
                selected_ids.add(candidate.doc_id)
        if take < minimum:
            needed = minimum - take
            for candidate in ranked:
                if candidate.doc_id in selected_ids:
                    continue
                selected.append(candidate)
                selected_ids.add(candidate.doc_id)
                needed -= 1
                if needed <= 0:
                    break

    for candidate in ranked:
        if candidate.doc_id not in selected_ids:
            selected.append(candidate)
            selected_ids.add(candidate.doc_id)

    selected.sort(key=lambda c: c.hybrid_score, reverse=True)
    return selected
