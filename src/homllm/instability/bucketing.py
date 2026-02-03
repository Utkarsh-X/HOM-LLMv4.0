"""
Historical bucketing (spec § Query Bucketing).

Bucket by: 1) Intent class, 2) Coarse embedding proximity (cosine ≥ threshold).
Prefer over-separation over false evidence propagation.
"""

from __future__ import annotations

from homllm.instability.constants import BUCKET_EMBEDDING_SIMILARITY_THRESHOLD
from homllm.instability.interfaces import RunRecord
from homllm.instability.utils import cosine_similarity


def bucket_runs(
    runs: tuple[RunRecord, ...],
    intent: str,
    reference_embedding: tuple[float, ...] | None = None,
) -> tuple[RunRecord, ...]:
    """
    Return runs that belong to the same bucket as the current query.

    - Same intent class (required).
    - If reference_embedding and run query_embedding are present, include run only if
      cosine(run.query_embedding, reference_embedding) ≥ threshold (over-separation:
      strict threshold).
    - If no reference_embedding or run has no query_embedding, include by intent only
      (conservative: do not exclude).
    """
    if not runs:
        return ()

    out: list[RunRecord] = []
    for r in runs:
        if r.intent != intent:
            continue
        if reference_embedding is not None and r.query_embedding is not None:
            sim = cosine_similarity(r.query_embedding, reference_embedding)
            if sim < BUCKET_EMBEDDING_SIMILARITY_THRESHOLD:
                continue
        out.append(r)
    return tuple(out)


__all__ = ["bucket_runs"]
