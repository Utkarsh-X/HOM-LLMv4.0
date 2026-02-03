"""
Cross-Run Instability — Staged evaluation (spec § Staged Evaluation Logic).

Stage 0: Cold-start guard. Stage 1: Mandatory veto (highest instability wins).
Stage 2: Refinement via embedding consistency only if no clear veto.
Anti-amplification: only raw counters influence labels (handled in failure_frequency).
"""

from __future__ import annotations

from homllm.instability.constants import (
    COLD_START_MIN_RUNS,
    SECONDARY_CONTRIBUTOR_THRESHOLD,
    VETO_THRESHOLD,
)
from homllm.instability.interfaces import (
    InstabilityResult,
    PrimaryLabelType,
    RunRecord,
    SignalScore,
)
from homllm.instability.signals import (
    answer_structure_variance,
    embedding_consistency,
    failure_frequency,
    metadata_variance,
    retrieval_overlap_instability,
)

# Stage 1 signals (spec: parallel evaluation; highest wins)
_STAGE1_SIGNALS: list[tuple[str, callable]] = [
    ("retrieval_overlap", retrieval_overlap_instability),
    ("metadata_variance", metadata_variance),
    ("failure_frequency", failure_frequency),
    ("answer_structure_variance", answer_structure_variance),
]


def run_instability(
    runs: tuple[RunRecord, ...],
    intent: str,
    reference_embedding: tuple[float, ...] | None = None,
) -> InstabilityResult:
    """
    Run Cross-Run Instability Detection (read-only diagnostic).

    - Buckets runs by intent + embedding proximity (≥ threshold).
    - Stage 0: evidence_volume < N → UNSTABLE_CONTEXT, medium confidence.
    - Stage 1: retrieval overlap, metadata variance, failure frequency, answer-structure;
      highest instability score wins immediately.
    - Stage 2: if no clear veto, use embedding consistency to disambiguate.
    - No mutation; no LLM calls; strongest signal wins; conservative bias.
    """
    from homllm.instability.bucketing import bucket_runs

    bucket = bucket_runs(runs, intent, reference_embedding)
    evidence_volume = len(bucket)

    # Stage 0: Cold-start guard
    if evidence_volume < COLD_START_MIN_RUNS:
        return InstabilityResult(
            primary_label="UNSTABLE_CONTEXT",
            confidence=0.5,
            evidence_volume=evidence_volume,
            explanation={"cold_start": 1.0},
            primary_deciding_signal="cold_start",
            secondary_contributors=(),
            cold_start=True,
            per_signal_scores=(),
            thresholds_triggered=("cold_start",),
        )

    # Stage 1: Compute all four signals; collect per-signal for audit
    scores: list[tuple[str, float, PrimaryLabelType | None]] = []
    for name, fn in _STAGE1_SIGNALS:
        score, label = fn(bucket)
        scores.append((name, score, label))

    # Highest instability wins (spec: no averaging)
    best_name = max(scores, key=lambda x: x[1])
    best_score = best_name[1]
    best_label = best_name[2]
    primary_name = best_name[0]

    # Threshold for "clear veto"
    thresholds_triggered: list[str] = []
    emb_score, emb_label = embedding_consistency(bucket)
    if best_score >= VETO_THRESHOLD:
        thresholds_triggered.append(primary_name)
    else:
        # Stage 2: Refinement via embedding consistency (spec: only if no clear veto)
        if emb_score >= VETO_THRESHOLD:
            best_score = emb_score
            best_label = emb_label
            primary_name = "embedding_consistency"
            thresholds_triggered.append(primary_name)
        else:
            best_label = "STABLE"
            primary_name = "embedding_consistency" if emb_score > 0 else "stage2_none"

    # Primary label: exactly one of STABLE | UNSTABLE_CONTEXT | UNSTABLE_REASONING
    primary_label: PrimaryLabelType = best_label if best_label is not None else "STABLE"

    # Secondary contributors (above mild threshold, excluding primary)
    secondary = [
        name for name, score, _ in scores
        if score >= SECONDARY_CONTRIBUTOR_THRESHOLD and name != primary_name
    ]
    if emb_score >= SECONDARY_CONTRIBUTOR_THRESHOLD and "embedding_consistency" != primary_name:
        secondary.append("embedding_consistency")

    # Per-signal scores for audit
    all_scores_dict: dict[str, float] = {}
    per_signal_list: list[SignalScore] = []
    for name, score, label in scores:
        all_scores_dict[name] = score
        per_signal_list.append(
            SignalScore(
                signal_name=name,
                score=score,
                label=label,
                threshold_triggered=score >= VETO_THRESHOLD,
            )
        )
    all_scores_dict["embedding_consistency"] = emb_score
    per_signal_list.append(
        SignalScore(
            signal_name="embedding_consistency",
            score=emb_score,
            label=emb_label,
            threshold_triggered=emb_score >= VETO_THRESHOLD,
        )
    )

    # Confidence: signal clarity (spec: correctness likelihood)
    confidence = min(1.0, 0.5 + 0.5 * best_score) if best_score > 0 else 0.5

    return InstabilityResult(
        primary_label=primary_label,
        confidence=confidence,
        evidence_volume=evidence_volume,
        explanation=all_scores_dict,
        primary_deciding_signal=primary_name,
        secondary_contributors=tuple(secondary),
        cold_start=False,
        per_signal_scores=tuple(per_signal_list),
        thresholds_triggered=tuple(thresholds_triggered),
    )


__all__ = ["run_instability"]
