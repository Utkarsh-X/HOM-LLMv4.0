"""Tier 3B: Adaptive Seed Gate (hybrid knee gate).

Replaces the static post_merge_candidates cap with a smoothed
RRF-gradient knee detector that adaptively determines the cutoff point.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homllm.retrieval.interfaces import Candidate

logger = logging.getLogger(__name__)


@dataclass
class KneeGateResult:
    """Result of adaptive knee gate."""

    candidates: list[Candidate]
    knee_position: int
    pre_knee_count: int
    post_knee_count: int
    min_k: int
    max_k: int


def hybrid_knee_gate(
    candidates: list[Candidate],
    *,
    min_k: int = 20,
    max_k: int = 150,
    relative_drop_threshold: float = 0.30,
) -> KneeGateResult:
    """Apply adaptive seed gate using smoothed RRF gradient detection.

    Instead of hard-capping at a fixed number, detect the "knee" where
    score quality drops off significantly. Enforce strict bounds [min_k, max_k].

    Algorithm:
    1. Sort candidates by hybrid_score descending (assumed already sorted)
    2. Compute score gradient: delta[i] = score[i] - score[i+1]
    3. Smooth gradient with 3-point moving average
    4. Find first position where smoothed gradient > relative_drop_threshold * score[i]
    5. Clamp result to [min_k, max_k]

    Args:
        candidates: Candidates sorted by hybrid_score descending.
        min_k: Minimum candidates to keep (floor).
        max_k: Maximum candidates to keep (ceiling).
        relative_drop_threshold: Relative score drop to trigger knee.

    Returns:
        KneeGateResult with filtered candidates and telemetry.
    """
    n = len(candidates)
    pre_count = n

    if n <= min_k:
        return KneeGateResult(
            candidates=candidates,
            knee_position=n,
            pre_knee_count=pre_count,
            post_knee_count=n,
            min_k=min_k,
            max_k=max_k,
        )

    scores = [c.hybrid_score for c in candidates]

    # Compute raw gradient
    gradients = []
    for i in range(n - 1):
        gradients.append(scores[i] - scores[i + 1])
    gradients.append(0.0)  # pad last position

    # 3-point moving average smoothing
    smoothed = []
    for i in range(len(gradients)):
        window = gradients[max(0, i - 1): min(len(gradients), i + 2)]
        smoothed.append(sum(window) / len(window))

    # Find knee: first position >= min_k where relative drop exceeds threshold
    knee = n  # default: keep all
    for i in range(min_k, min(n - 1, max_k)):
        if scores[i] > 0:
            relative_drop = smoothed[i] / scores[i]
            if relative_drop > relative_drop_threshold:
                knee = i
                break

    # Clamp to bounds
    knee = max(min_k, min(knee, max_k, n))

    result = candidates[:knee]

    logger.info(
        "[KNEE_GATE] pre=%d knee_position=%d post=%d min_k=%d max_k=%d",
        pre_count,
        knee,
        len(result),
        min_k,
        max_k,
    )

    return KneeGateResult(
        candidates=result,
        knee_position=knee,
        pre_knee_count=pre_count,
        post_knee_count=len(result),
        min_k=min_k,
        max_k=max_k,
    )
