"""
Structural Explanation Gap Detection — Staged pipeline (spec §5).

Stage 1: Mandatory escalation (rules + history). Most severe dominates; no downgrade.
Stage 2: Semantic refinement (embedding) only when Stage 1 is SHALLOW_OK.
Stage 3: Optional classifier upgrade only. Ambiguity → escalate.
"""

from __future__ import annotations

from homllm.explanation_gap.classifier_stub import classifier_upgrade_only
from homllm.explanation_gap.constants import (
    COLD_START_CONFIDENCE,
    EMBEDDING_UPGRADE_THRESHOLD,
    SEED_EXPLANATORY,
    SEED_FACTUAL,
    SEED_ILLUSTRATIVE,
)
from homllm.explanation_gap.embedding_refinement import embedding_refinement
from homllm.explanation_gap.history import historical_depth_escalation
from homllm.explanation_gap.interfaces import (
    DepthLabelType,
    ExplanationGapResult,
    HistoryDepthStats,
    SignalOutput,
    max_severity,
)
from homllm.explanation_gap.rules import rule_based_depth


def run_explanation_gap(
    query: str,
    history_stats: HistoryDepthStats | None = None,
    query_embedding: tuple[float, ...] | None = None,
    illustrative_centroid: tuple[float, ...] | None = None,
    explanatory_centroid: tuple[float, ...] | None = None,
    factual_centroid: tuple[float, ...] | None = None,
    run_stage3: bool = True,
) -> ExplanationGapResult:
    """
    Run Structural Explanation Gap Detection (read-only diagnostic).

    Stage 1: Rule-based patterns + historical depth recurrence. Most severe trigger wins.
    Stage 2: Only if Stage 1 is SHALLOW_OK; embedding refinement may upgrade.
    Stage 3: Optional classifier upgrade only (stub: no-op).
    No downgrade; ambiguity → escalate. Advisory only.
    """
    # Stage 1 — Mandatory escalation (rules + history)
    rule_label, rule_trigger, rule_signals = rule_based_depth(query)
    hist_label, hist_trigger, hist_signals = historical_depth_escalation(
        rule_label, history_stats
    )
    stage1_label = max_severity(rule_label, hist_label)
    deciding_trigger = rule_trigger if stage1_label == rule_label else hist_trigger
    per_signal: list[SignalOutput] = list(rule_signals) + list(hist_signals)

    # Evidence volume
    evidence_volume = history_stats.runs_in_bucket if history_stats else 0
    cold_start = evidence_volume < 2

    # Stage 2 — Semantic refinement only when Stage 1 is SHALLOW_OK
    if stage1_label == "SHALLOW_OK":
        stage2_label, stage2_trigger, stage2_signals = embedding_refinement(
            stage1_label,
            query_embedding,
            illustrative_centroid,
            explanatory_centroid,
            factual_centroid,
        )
        if stage2_label != "SHALLOW_OK":
            stage1_label = stage2_label
            deciding_trigger = stage2_trigger
        per_signal.extend(stage2_signals)
    else:
        # No Stage 2 when already escalated
        per_signal.append(
            SignalOutput(
                signal_name="embedding_refinement",
                label=None,
                trigger="Embedding(skip_not_shallow)",
                score_or_note="",
            )
        )

    # Stage 3 — Optional upgrade only (stub)
    if run_stage3:
        stage3_label, stage3_trigger, stage3_signals = classifier_upgrade_only(
            stage1_label, query
        )
        # Stub never upgrades; if real classifier did upgrade, use it
        stage1_label = max_severity(stage1_label, stage3_label)
        if stage1_label != stage3_label and stage3_label != "SHALLOW_OK":
            deciding_trigger = stage3_trigger
        per_signal.extend(stage3_signals)

    final_label: DepthLabelType = stage1_label

    # Confidence: bounded; cold-start medium; no inflation from single signal
    if cold_start:
        confidence = COLD_START_CONFIDENCE
    else:
        confidence = min(0.95, 0.5 + 0.15 * evidence_volume / 20.0)

    rationale = f"Deciding: {deciding_trigger}; evidence_volume={evidence_volume}"

    return ExplanationGapResult(
        label=final_label,
        confidence=confidence,
        evidence_volume=evidence_volume,
        rationale=rationale,
        deciding_trigger=deciding_trigger,
        per_signal_outputs=tuple(per_signal),
        cold_start=cold_start,
    )


def run_explanation_gap_with_embedder(
    query: str,
    embedder: "EmbedderLike",
    history_stats: HistoryDepthStats | None = None,
    run_stage3: bool = True,
) -> ExplanationGapResult:
    """
    Convenience: run pipeline with an embedder. Embeds query and seed phrases
    for Stage 2 centroid comparison. embedder must have embed_query() and .dimension.
    """
    query_emb = _embed_if_available(embedder, query)
    ill_centroid = _embed_if_available(embedder, SEED_ILLUSTRATIVE)
    exp_centroid = _embed_if_available(embedder, SEED_EXPLANATORY)
    fact_centroid = _embed_if_available(embedder, SEED_FACTUAL)
    return run_explanation_gap(
        query,
        history_stats=history_stats,
        query_embedding=query_emb,
        illustrative_centroid=ill_centroid,
        explanatory_centroid=exp_centroid,
        factual_centroid=fact_centroid,
        run_stage3=run_stage3,
    )


def _embed_if_available(embedder: "EmbedderLike", text: str) -> tuple[float, ...] | None:
    """Return embedding as tuple of floats, or None on failure."""
    try:
        v = embedder.embed_query(text)
        if hasattr(v, "values"):
            return tuple(v.values)
        return tuple(v) if v is not None else None
    except Exception:
        return None


try:
    from typing import Protocol
except ImportError:
    Protocol = object  # type: ignore


class EmbedderLike(Protocol):
    """Protocol: embed_query(text) -> vector-like with .values or tuple of float."""

    def embed_query(self, query: str): ...


__all__ = ["run_explanation_gap", "run_explanation_gap_with_embedder"]
