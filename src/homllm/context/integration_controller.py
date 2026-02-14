"""Set-level integration controller for context-stage budget modulation.

This module is context-only. It does not alter ranking order or semantics.
It produces continuous, query-agnostic signals that help the budget allocator
avoid pathological single-file concentration and early coverage plateau.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from homllm.context.synthesis_profile import extract_query_concepts
from homllm.context.interfaces import ScoredBlock


@dataclass(frozen=True)
class ContextIntegrationProfile:
    integration_pressure: float
    file_dispersion: float
    coverage_slope: float
    redundancy_level: float
    semantic_entropy: float


def compute_context_integration_profile(
    query: str,
    ranked_blocks: list[ScoredBlock],
    top_n: int = 20,
) -> ContextIntegrationProfile:
    """
    Compute set-geometry signals from top-N ranked blocks.

    Constraints:
    - Query-agnostic: generic concept extraction only (no keyword rules)
    - Continuous: no thresholds, no branching on query type
    - Deterministic: pure function
    """
    if not ranked_blocks:
        return ContextIntegrationProfile(
            integration_pressure=0.0,
            file_dispersion=0.0,
            coverage_slope=0.0,
            redundancy_level=0.0,
            semantic_entropy=0.0,
        )

    n = min(max(int(top_n), 1), len(ranked_blocks))
    top = ranked_blocks[:n]

    # file_dispersion: distinct_files / N
    files = [sb.block.file for sb in top if sb.block.file]
    distinct_files = len(set(files))
    file_dispersion = (distinct_files / max(n, 1)) if n > 0 else 0.0

    # coverage_slope: early derivative of coverage curve (normalized)
    concepts = [c.lower() for c in extract_query_concepts(query)]
    coverage_curve = _coverage_curve(top, concepts)
    coverage_slope = _early_slope(coverage_curve)

    # redundancy_level: average span overlap among top-N blocks
    redundancy_level = _avg_span_overlap([sb.block for sb in top])

    # semantic_entropy: entropy of semantic scores (normalized)
    semantic_entropy = _normalized_entropy([sb.semantic_score for sb in top])

    # integration_pressure (all terms normalized 0-1)
    integration_pressure = _clamp01(
        0.35 * (1.0 - _clamp01(file_dispersion))
        + 0.25 * (1.0 - _clamp01(coverage_slope))
        + 0.20 * _clamp01(redundancy_level)
        + 0.20 * _clamp01(semantic_entropy)
    )

    return ContextIntegrationProfile(
        integration_pressure=integration_pressure,
        file_dispersion=_clamp01(file_dispersion),
        coverage_slope=_clamp01(coverage_slope),
        redundancy_level=_clamp01(redundancy_level),
        semantic_entropy=_clamp01(semantic_entropy),
    )


def _coverage_curve(top: list[ScoredBlock], concepts: list[str]) -> list[float]:
    if not concepts:
        return []
    covered: set[str] = set()
    curve: list[float] = []
    concept_set = set(concepts)
    for sb in top:
        covered |= _concepts_for_block(sb, concept_set)
        curve.append(len(covered) / max(len(concept_set), 1))
    return curve


def _concepts_for_block(sb: ScoredBlock, concept_set: set[str]) -> set[str]:
    # Minimal, query-agnostic concept match across file + symbol + preview.
    haystack = " ".join(
        [
            sb.block.file or "",
            sb.block.symbol_id or "",
            (sb.block.content or "")[:300],
        ]
    ).lower()
    return {c for c in concept_set if c and c in haystack}


def _early_slope(curve: list[float]) -> float:
    if not curve:
        return 0.0
    if len(curve) == 1:
        return _clamp01(curve[0])
    gains = [curve[i] - curve[i - 1] for i in range(1, len(curve))]
    k = min(5, len(gains))
    if k <= 0:
        return 0.0
    avg_gain = sum(gains[:k]) / k
    return _clamp01(avg_gain)


def _avg_span_overlap(blocks) -> float:
    if len(blocks) < 2:
        return 0.0
    overlaps: list[float] = []
    for i, a in enumerate(blocks):
        for b in blocks[i + 1 :]:
            overlaps.append(_span_overlap_ratio(a, b))
    if not overlaps:
        return 0.0
    return _clamp01(sum(overlaps) / len(overlaps))


def _span_overlap_ratio(a, b) -> float:
    if a.file != b.file:
        return 0.0
    if a.start_line is None or a.end_line is None:
        return 0.0
    if b.start_line is None or b.end_line is None:
        return 0.0
    start = max(int(a.start_line), int(b.start_line))
    end = min(int(a.end_line), int(b.end_line))
    if start > end:
        return 0.0
    overlap = end - start + 1
    length = min(
        max(int(a.end_line) - int(a.start_line) + 1, 1),
        max(int(b.end_line) - int(b.start_line) + 1, 1),
    )
    return overlap / length


def _normalized_entropy(values: list[float]) -> float:
    positives = [float(v) for v in values if v is not None and v > 0]
    if len(positives) <= 1:
        return 0.0
    total = sum(positives)
    if total <= 0:
        return 0.0
    probs = [v / total for v in positives]
    entropy = -sum(p * math.log(p) for p in probs if p > 0)
    max_entropy = math.log(len(probs))
    return entropy / max_entropy if max_entropy > 0 else 0.0


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value

