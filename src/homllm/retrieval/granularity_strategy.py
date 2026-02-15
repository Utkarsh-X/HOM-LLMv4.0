"""Granularity-aware candidate mixing strategy."""

from __future__ import annotations

from homllm.common.types import Intent
from homllm.retrieval.interfaces import Candidate


def apply_granularity_mix(
    candidates: list[Candidate],
    intent: Intent,
    mix_profiles: dict | None = None,
) -> list[Candidate]:
    """Ensure retrieval set contains a useful mix of granularities."""
    if not candidates:
        return candidates

    profiles = mix_profiles or {}
    intent_key = str(intent.value if isinstance(intent, Intent) else intent).strip().upper()
    constraints = profiles.get(intent_key) or profiles.get("UNKNOWN") or {}

    ranked = sorted(candidates, key=lambda c: c.hybrid_score, reverse=True)
    buckets: dict[str, list[Candidate]] = {"fine": [], "medium": [], "coarse": [], "unknown": []}
    for candidate in ranked:
        level = (candidate.granularity_level or "unknown").lower()
        buckets[level if level in buckets else "unknown"].append(candidate)

    selected_ids: set[str] = set()
    selected: list[Candidate] = []

    for level in ("fine", "medium", "coarse"):
        level_bounds = constraints.get(level, {})
        minimum = int(level_bounds.get("min", 0))
        maximum = int(level_bounds.get("max", 0))
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
