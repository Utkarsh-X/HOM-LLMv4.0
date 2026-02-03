"""
Cross-Run Instability — Deterministic helpers (cosine similarity, Jaccard).

No LLM calls. Frozen logic only.
"""

from __future__ import annotations

import math


def cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Frozen cosine similarity in [0, 1] for normalized vectors; [−1, 1] in general."""
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Jaccard (intersection / union). Returns 0 if both empty."""
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return inter / union


def variance(values: tuple[float, ...]) -> float:
    """Population variance. Returns 0 if fewer than 2 values."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return sum((x - mean) ** 2 for x in values) / n


def normalized_variance(values: tuple[float, ...]) -> float:
    """Variance normalized to [0, 1] using (var / (1 + var)) or by max. Returns 0 if n<2."""
    v = variance(values)
    if v <= 0:
        return 0.0
    # Cap so score stays in [0, 1]; use tanh-like scaling
    return min(1.0, v / (1.0 + v))
