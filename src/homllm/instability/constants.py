"""
Cross-Run Instability Detection — Frozen constants (spec § Freeze Conditions).

Structural feature thresholds, bucket invariants, cold-start constants.
No learning loops, no runtime mutation.
"""

from __future__ import annotations

# Cold-start guard (spec § Stage 0): evidence_volume < N → UNSTABLE_CONTEXT
COLD_START_MIN_RUNS = 2

# Bucketing: coarse embedding proximity (spec § Query Bucketing)
# Cosine similarity ≥ threshold → same bucket. Prefer over-separation.
BUCKET_EMBEDDING_SIMILARITY_THRESHOLD = 0.85

# Stage 1: mandatory veto — highest instability score wins
# Stage 2: if max score below this, refine via embedding consistency
VETO_THRESHOLD = 0.5

# Secondary contributors: signals above this (mild) are recorded
SECONDARY_CONTRIBUTOR_THRESHOLD = 0.3

# Answer-structure: refusal/surrender markers (structural only)
REFUSAL_MARKERS = (
    "not in context",
    "i don't have",
    "i cannot",
    "i'm unable",
    "no information",
    "not available",
    "cannot determine",
    "insufficient context",
)

__all__ = [
    "BUCKET_EMBEDDING_SIMILARITY_THRESHOLD",
    "COLD_START_MIN_RUNS",
    "REFUSAL_MARKERS",
    "SECONDARY_CONTRIBUTOR_THRESHOLD",
    "VETO_THRESHOLD",
]
