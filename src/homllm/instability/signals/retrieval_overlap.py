"""
Retrieval Overlap Statistics (spec § Signal 1).

Jaccard / set similarity on chunk IDs. Low overlap → UNSTABLE_CONTEXT.
"""

from __future__ import annotations

from homllm.instability.interfaces import PrimaryLabelType, RunRecord
from homllm.instability.utils import jaccard_similarity


def retrieval_overlap_instability(runs: tuple[RunRecord, ...]) -> tuple[float, PrimaryLabelType | None]:
    """
    Instability score from retrieval overlap. Higher = more unstable.
    Low pairwise Jaccard on chunk IDs → UNSTABLE_CONTEXT.
    """
    if len(runs) < 2:
        return 0.0, None
    sets = [set(r.chunk_ids) for r in runs]
    total = 0.0
    count = 0
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            total += jaccard_similarity(sets[i], sets[j])
            count += 1
    mean_jaccard = total / count if count else 0.0
    # Low overlap → high instability
    score = 1.0 - mean_jaccard
    label: PrimaryLabelType | None = "UNSTABLE_CONTEXT" if score > 0.5 else None
    return score, label
