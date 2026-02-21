"""
Context Quality Kernel — Orchestrator.

Computes all 7 metrics from pipeline outputs and produces a MetricRecord.
Optionally tracks percentile windows for normalization.

Usage:
    kernel = ContextQualityKernel()

    # After ranking:
    ranking_metrics = kernel.compute_ranking_metrics(ranking_output, rank_config)

    # After context assembly:
    record = kernel.evaluate(
        ranking_output=ranking_output,
        rank_config=rank_config,
        context_artifact=context_artifact,
        run_id="run_001",
    )

    # Access raw values:
    print(record.semantic_strength)   # M1
    print(record.score_separation)    # M5
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from homllm.quality.metrics import (
    semantic_strength,
    query_term_recall,
    file_entropy,
    content_overlap,
    score_separation,
    reranker_influence,
    budget_utilization,
)
from homllm.quality.percentile import PercentileTracker
from homllm.quality.schema import MetricRecord, MetricStorage

if TYPE_CHECKING:
    from pathlib import Path
    from homllm.context.interfaces import ContextArtifact
    from homllm.ranking.interfaces import RankConfig, RankingOutput

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RankingMetrics:
    """Intermediate result: metrics computed after ranking, before context assembly."""

    score_separation: float
    reranker_influence: float
    candidate_count: int
    reranker_available: bool


class ContextQualityKernel:
    """
    Deterministic context quality evaluator.

    Computes 7 metrics from pipeline outputs. No thresholds, no LLM calls,
    no language-specific assumptions.

    Lifecycle:
        1. Instantiate once per process (or per pipeline run).
        2. Call compute_ranking_metrics() after ranking completes.
        3. Call evaluate() after context assembly completes.
        4. MetricRecord is returned and optionally persisted.
    """

    def __init__(
        self,
        tracker: Optional[PercentileTracker] = None,
        storage: Optional[MetricStorage] = None,
    ) -> None:
        """
        Args:
            tracker: Optional percentile tracker for normalization. If None,
                     percentile tracking is disabled (raw values only).
            storage: Optional JSONL storage for metric persistence. If None,
                     records are returned but not persisted.
        """
        self._tracker = tracker
        self._storage = storage

    # =========================================================================
    # STAGE 1: Post-Ranking Metrics (M5, M6)
    # =========================================================================

    def compute_ranking_metrics(
        self,
        ranking_output: "RankingOutput",
        rank_config: "RankConfig",
    ) -> RankingMetrics:
        """
        Compute ranking-stage metrics on the full ranked surface.

        M5 and M6 are computed from RankingOutput.debug_traces.

        IMPORTANT: RankingOutput.debug_traces may be post-selection (after
        dedup/SetOpt/MMR). When ranking_geometry telemetry is available in
        metadata, M6 is read from it instead — ranking_geometry is always
        computed on the full pre-selection surface inside the ranking pipeline.

        Args:
            ranking_output: Output from ranking pipeline.
            rank_config: Ranking configuration (for rerank_alpha).

        Returns:
            RankingMetrics with M5 and M6.
        """
        traces = ranking_output.debug_traces
        metadata = ranking_output.metadata

        final_scores = [t.final_score for t in traces]
        rerank_scores = [t.rerank_score for t in traces]

        m5 = score_separation(final_scores)

        # M6: Prefer ranking_geometry telemetry (computed on full ranked surface)
        # over recomputation from potentially post-selection debug_traces.
        geometry = metadata.ranking_geometry
        if geometry and "rerank_contribution_percent" in geometry:
            m6 = float(geometry["rerank_contribution_percent"]) / 100.0
        else:
            # Fallback: recompute from traces (may be post-selection scope)
            alpha = getattr(rank_config, "rerank_alpha", 0.32)
            m6 = reranker_influence(
                final_scores=final_scores,
                rerank_scores=rerank_scores,
                rerank_alpha=alpha,
            )

        return RankingMetrics(
            score_separation=round(m5, 6),
            reranker_influence=round(m6, 6),
            candidate_count=metadata.candidate_count,
            reranker_available=metadata.reranker_used and not metadata.reranker_unavailable,
        )

    # =========================================================================
    # STAGE 2: Full Evaluation (M1–M7)
    # =========================================================================

    def evaluate(
        self,
        ranking_output: "RankingOutput",
        rank_config: "RankConfig",
        context_artifact: "ContextArtifact",
        run_id: str,
    ) -> MetricRecord:
        """
        Compute all 7 metrics and produce a MetricRecord.

        Called AFTER context assembly completes, BEFORE generation.

        Args:
            ranking_output: Output from ranking pipeline (for M5, M6, M1 scores).
            rank_config: Ranking configuration (for rerank_alpha).
            context_artifact: Final context artifact (for M1, M2, M3, M4, M7).
            run_id: Unique identifier for this pipeline run.

        Returns:
            Frozen MetricRecord with all 7 metrics.

        Raises:
            AssertionError: If candidate_count < block_count (scope violation).
        """
        # Stage 1: Ranking metrics
        ranking = self.compute_ranking_metrics(ranking_output, rank_config)

        # Scope guard: ranked surface must be >= selected blocks
        block_count = len(context_artifact.blocks)
        assert ranking.candidate_count >= block_count, (
            f"Scope violation: candidate_count ({ranking.candidate_count}) "
            f"< block_count ({block_count}). M5/M6 require the full ranked surface."
        )

        # Build lookup: candidate_id → rerank_score
        trace_lookup: dict[str, float] = {
            t.candidate_id: t.rerank_score
            for t in ranking_output.debug_traces
        }

        # Extract context block data
        blocks = context_artifact.blocks
        block_contents = [b.content for b in blocks]
        block_files = [b.file for b in blocks]

        # M1: Semantic Strength
        # Join context blocks to ranking traces to get rerank scores
        block_rerank_scores = []
        for block in blocks:
            score = trace_lookup.get(block.block_id)
            if score is not None:
                block_rerank_scores.append(score)
        m1 = semantic_strength(block_rerank_scores)

        # M2: Query Term Recall
        query_text = context_artifact.provenance.get("query", "")
        m2 = query_term_recall(query_text, block_contents)

        # M3: File Entropy
        m3 = file_entropy(block_files)

        # M4: Content Overlap
        m4 = content_overlap(block_contents)

        # M7: Budget Utilization
        m7 = budget_utilization(context_artifact.used_tokens, context_artifact.token_budget)

        # Build record
        unique_files = len(set(block_files))
        record = MetricRecord(
            query_id=context_artifact.query_id,
            run_id=run_id,
            timestamp_utc=MetricRecord.utc_now(),
            score_separation=round(ranking.score_separation, 6),
            reranker_influence=round(ranking.reranker_influence, 6),
            semantic_strength=round(m1, 6),
            query_term_recall=round(m2, 6),
            file_entropy=round(m3, 6),
            content_overlap=round(m4, 6),
            budget_utilization=round(m7, 6),
            block_count=len(blocks),
            unique_file_count=unique_files,
            candidate_count=ranking.candidate_count,
            reranker_available=ranking.reranker_available,
        )

        # Update percentile tracker
        if self._tracker is not None:
            self._tracker.add("semantic_strength", record.semantic_strength)
            self._tracker.add("query_term_recall", record.query_term_recall)
            self._tracker.add("file_entropy", record.file_entropy)
            self._tracker.add("content_overlap", record.content_overlap)
            self._tracker.add("score_separation", record.score_separation)
            self._tracker.add("reranker_influence", record.reranker_influence)
            self._tracker.add("budget_utilization", record.budget_utilization)

        # Persist
        if self._storage is not None:
            self._storage.append(record)

        logger.debug(
            "Context quality: M1=%.3f M2=%.3f M3=%.3f M4=%.3f M5=%.3f M6=%.3f M7=%.3f",
            record.semantic_strength,
            record.query_term_recall,
            record.file_entropy,
            record.content_overlap,
            record.score_separation,
            record.reranker_influence,
            record.budget_utilization,
        )

        return record

    # =========================================================================
    # PERCENTILE QUERIES (optional — only if tracker is configured)
    # =========================================================================

    def percentiles(self, record: MetricRecord) -> dict[str, float]:
        """
        Compute percentile positions for all metrics in a record.

        Returns:
            Dict mapping metric name → percentile (0.0 to 1.0).
            Returns all 0.5 if no tracker is configured.
        """
        if self._tracker is None:
            return {name: 0.5 for name in (
                "semantic_strength", "query_term_recall", "file_entropy",
                "content_overlap", "score_separation", "reranker_influence",
                "budget_utilization",
            )}

        return {
            "semantic_strength": self._tracker.percentile("semantic_strength", record.semantic_strength),
            "query_term_recall": self._tracker.percentile("query_term_recall", record.query_term_recall),
            "file_entropy": self._tracker.percentile("file_entropy", record.file_entropy),
            "content_overlap": self._tracker.percentile("content_overlap", record.content_overlap),
            "score_separation": self._tracker.percentile("score_separation", record.score_separation),
            "reranker_influence": self._tracker.percentile("reranker_influence", record.reranker_influence),
            "budget_utilization": self._tracker.percentile("budget_utilization", record.budget_utilization),
        }
