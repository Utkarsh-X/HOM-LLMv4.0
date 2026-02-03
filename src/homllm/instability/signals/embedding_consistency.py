"""
Embedding Consistency (spec § Signal 4, § Stage 2).

Variance of frozen centroid embeddings across runs. Semantic drift → UNSTABLE_CONTEXT proxy.
"""

from __future__ import annotations

from homllm.instability.interfaces import PrimaryLabelType, RunRecord


def embedding_consistency(runs: tuple[RunRecord, ...]) -> tuple[float, PrimaryLabelType | None]:
    """
    Instability from variance of context centroid embeddings across runs.
    High variance → UNSTABLE_CONTEXT. Used in Stage 2 refinement.
    """
    with_centroid = [r for r in runs if r.context_centroid_embedding is not None]
    if len(with_centroid) < 2:
        return 0.0, None
    dim = len(with_centroid[0].context_centroid_embedding)  # type: ignore[union-attr]
    centroids = [r.context_centroid_embedding for r in with_centroid]  # type: ignore[union-attr]
    mean_centroid = tuple(
        sum(c[i] for c in centroids) / len(centroids)
        for i in range(dim)
    )
    mean_sq_dist = sum(
        sum((c[i] - mean_centroid[i]) ** 2 for i in range(dim))
        for c in centroids
    ) / len(centroids)
    score = min(1.0, mean_sq_dist / (1.0 + mean_sq_dist))
    label: PrimaryLabelType | None = "UNSTABLE_CONTEXT" if score > 0.5 else None
    return score, label
