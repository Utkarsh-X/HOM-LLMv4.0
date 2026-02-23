"""Ranking pipeline orchestrator."""

from collections import Counter
import logging
import math
import time
from typing import Optional

from homllm.ranking.dedup_structural import StructuralDeduplicator
from homllm.ranking.features import FeatureEnricher
from homllm.ranking.fusion import ScoreFusion
from homllm.ranking.graph_propagation import NeighborBoosting
from homllm.ranking.interfaces import (
    DebugTrace,
    RankConfig,
    RankMetadata,
    RankingInput,
    RankingOutput,
)
from homllm.ranking.mmr_selection import select_mmr
from homllm.ranking.signal_profile import compute_signal_profile
from homllm.ranking.reranker import QwenReranker
from homllm.ranking.set_optimizer import SetOptimizer, SetObjectiveWeights, extract_query_concepts

logger = logging.getLogger(__name__)


class RankingPipeline:
    """
    Main ranking pipeline.
    
    Flow: Candidates → Pre-filter → Feature Enrichment → Base Fusion → [Reranker] → Final Fusion → Dedup → Output
    
    Invariants:
    - RNK-001: Same inputs → same ranking
    - RNK-002: Does not modify candidates
    - RNK-003: Does not call generation
    - RNK-004: All weights in config
    - RNK-005: Reranker is optional/pluggable
    """

    def __init__(
        self,
        config: RankConfig,
        callgraph: Optional[dict] = None,
        reranker: Optional[object] = None,
    ):
        """
        Initialize ranking pipeline.
        
        Args:
            config: Ranking configuration
            callgraph: Call graph for structural features (optional)
            reranker: Reranker instance (default: QwenReranker)
        """
        self.config = config
        self.callgraph = callgraph or {}
        self.feature_enricher = FeatureEnricher(
            self.callgraph,
            graph_max_depth=config.graph_max_depth,
            graph_anchor_k=config.graph_anchor_k,
        )
        self.fusion = ScoreFusion()
        self.deduplicator = StructuralDeduplicator(
            config.dedup_file_entropy_threshold
        )
        self.reranker = reranker or (
            QwenReranker(
                model_name=config.reranker_model,
                device=config.reranker_device,
            )
            if config.reranker_enabled
            else None
        )

    def rank(self, input_data: RankingInput) -> RankingOutput:
        """
        Execute ranking pipeline.
        
        Args:
            input_data: Ranking input with query, candidates, and config
        
        Returns:
            RankingOutput with ranked candidates, debug traces, and metadata
        
        Guarantees:
        - Deterministic for same inputs
        - Never modifies candidates
        - All weights from config
        """
        start_time = time.time()

        try:
            # 1. Pre-filter (if needed - currently no filtering)
            candidates = list(input_data.candidates)

            # 2. Feature enrichment
            features = self.feature_enricher.enrich(candidates, input_data.query)
            distance_map = self.feature_enricher.get_distance_map(candidates)

            # 3. Base fusion
            base_scores: dict[str, float] = {}
            for candidate in candidates:
                candidate_features = features.get(candidate.doc_id)
                if candidate_features:
                    base_scores[candidate.doc_id] = self.fusion.compute_base_score(
                        candidate_features, self.config
                    )

            # Extract query concepts once for set optimization.
            query_concepts = extract_query_concepts(input_data.query)

            # 4. Reranker (optional)
            rerank_scores: dict[str, float] = {}
            reranked_doc_ids: set[str] = set()
            reranker_used = False
            reranker_unavailable = False
            reranker_contract_diag: dict[str, float | str] = {
                "rerank_input_token_length": 0.0,
                "truncation_rate": 0.0,
                "instruction_variant": "none",
                "raw_logit_mean": 0.0,
                "raw_logit_std": 0.0,
                "sigmoid_mean": 0.0,
                "sigmoid_std": 0.0,
            }

            if self.config.reranker_enabled and self.reranker:
                if self.reranker.healthcheck():
                    try:
                        # Get top M candidates for reranking
                        top_m = min(self.config.reranker_top_m, len(candidates))
                        top_candidates = sorted(
                            candidates,
                            key=lambda c: (-base_scores.get(c.doc_id, 0.0), c.doc_id),
                        )[:top_m]

                        # Extract documents
                        documents = [
                            c.content if c.content else c.doc_id
                            for c in top_candidates
                        ]

                        # Batch rerank (timed for diagnostics)
                        rerank_start = time.perf_counter()
                        scores = self.reranker.batch_score(
                            input_data.query, documents
                        )
                        if hasattr(self.reranker, "get_last_batch_diagnostics"):
                            diag = self.reranker.get_last_batch_diagnostics()
                            if isinstance(diag, dict):
                                reranker_contract_diag.update(diag)
                        rerank_duration_ms = (time.perf_counter() - rerank_start) * 1000
                        print(f"[RERANK_PHASE] candidates_reranked={len(documents)} duration_ms={rerank_duration_ms:.1f}", flush=True)

                        # Map scores back to candidates
                        for candidate, score in zip(top_candidates, scores):
                            rerank_scores[candidate.doc_id] = score
                            reranked_doc_ids.add(candidate.doc_id)

                        reranker_used = True

                    except Exception as e:
                        logger.error(f"Reranker failed: {e}")
                        reranker_unavailable = True
                else:
                    reranker_unavailable = True
                    logger.warning("Reranker enabled but healthcheck failed.")
            else:
                reranker_unavailable = not self.config.reranker_enabled

            profile = None
            if self.config.phase2_enabled:
                profile = compute_signal_profile(candidates, base_scores, distance_map)

            alpha = max(0.0, min(float(self.config.rerank_alpha), 0.35))
            gamma = max(0.0, float(self.config.struct_gamma))
            rerank_subset = [rerank_scores[doc_id] for doc_id in reranked_doc_ids]
            rerank_mean = 0.0
            rerank_std = 0.0
            if rerank_subset:
                rerank_mean = sum(rerank_subset) / float(len(rerank_subset))
                rerank_std = math.sqrt(self._variance(rerank_subset))

            # 5. Stage 2 geometry: bounded, zero-centered rerank refinement.
            scored_candidates: list[tuple[Candidate, float, DebugTrace]] = []

            for candidate in candidates:
                candidate_features = features.get(candidate.doc_id)
                if not candidate_features:
                    continue

                base_score = base_scores.get(candidate.doc_id, 0.0)
                rerank_score = rerank_scores.get(candidate.doc_id, 0.0)
                rerank_delta = (
                    rerank_score - rerank_mean
                    if candidate.doc_id in reranked_doc_ids
                    else 0.0
                )
                struct_bonus = self.fusion.compute_struct_bonus(
                    candidate_features, self.config
                )

                final_score = (
                    base_score
                    + alpha * rerank_delta
                    + gamma * struct_bonus
                )

                # Create debug trace
                trace = DebugTrace(
                    candidate_id=candidate.doc_id,
                    base_score=base_score,
                    rerank_score=rerank_score,
                    struct_bonus=struct_bonus,
                    final_score=final_score,
                    features=candidate_features,
                    provenance=candidate.provenance,
                    rerank_evaluated=candidate.doc_id in reranked_doc_ids,
                )

                scored_candidates.append((candidate, final_score, trace))

            # Phase 2: Two-pass ranking with graph propagation
            if (
                self.config.phase2_enabled
                and self.config.two_pass_enabled
                and profile
                and (
                    profile.avg_graph_distance < 2.5
                    or profile.unique_files > 3
                )
            ):
                scored_candidates.sort(key=lambda x: (-x[1], x[0].doc_id))
                seed_k = min(self.config.two_pass_seed_k, len(scored_candidates))
                seed_map: dict[str, float] = {}
                for candidate, score, _ in scored_candidates[:seed_k]:
                    if candidate.symbol_id:
                        seed_map[candidate.symbol_id] = max(
                            seed_map.get(candidate.symbol_id, 0.0), score
                        )
                propagator = NeighborBoosting(
                    self.callgraph,
                    max_depth=self.config.two_pass_max_depth,
                    decay=self.config.two_pass_decay,
                )
                propagated = propagator.propagate(seed_map)
                max_prop = max(propagated.values()) if propagated else 0.0
                if max_prop > 0:
                    propagated = {k: v / max_prop for k, v in propagated.items()}

                rescored: list[tuple[Candidate, float, DebugTrace]] = []
                for candidate, base_final, trace in scored_candidates:
                    candidate_features = features.get(candidate.doc_id)
                    if not candidate_features:
                        continue
                    prop_score = (
                        propagated.get(candidate.symbol_id, 0.0)
                        if candidate.symbol_id
                        else 0.0
                    )
                    struct_bonus = 0.0
                    if candidate_features.is_entrypoint:
                        struct_bonus += self.config.struct_entrypoint_bonus
                    if candidate_features.has_decorator:
                        struct_bonus += self.config.struct_decorator_bonus
                    struct_bonus += prop_score * self.config.struct_callgraph_bonus
                    struct_bonus = min(struct_bonus, self.config.struct_bonus_cap)

                    final_score = (
                        trace.base_score
                        + (
                            alpha * (trace.rerank_score - rerank_mean)
                            if candidate.doc_id in reranked_doc_ids
                            else 0.0
                        )
                        + gamma * struct_bonus
                    )
                    trace = DebugTrace(
                        candidate_id=trace.candidate_id,
                        base_score=trace.base_score,
                        rerank_score=trace.rerank_score,
                        struct_bonus=struct_bonus,
                        final_score=final_score,
                        features=trace.features,
                        provenance=trace.provenance,
                        rerank_evaluated=trace.rerank_evaluated,
                    )
                    rescored.append((candidate, final_score, trace))

                scored_candidates = rescored

            geometry_metrics = self._compute_geometry_metrics(
                scored_candidates=scored_candidates,
                reranked_doc_ids=reranked_doc_ids,
                rerank_mean=rerank_mean,
                rerank_std=rerank_std,
                alpha=alpha,
            )
            geometry_metrics.update(reranker_contract_diag)

            # Rerank coverage telemetry
            total_candidates = len(scored_candidates)
            n_reranked = sum(1 for _, _, t in scored_candidates if t.rerank_evaluated)
            n_unevaluated = total_candidates - n_reranked
            geometry_metrics["percent_reranked"] = round(
                100.0 * n_reranked / total_candidates, 1
            ) if total_candidates > 0 else 0.0
            geometry_metrics["percent_unevaluated"] = round(
                100.0 * n_unevaluated / total_candidates, 1
            ) if total_candidates > 0 else 0.0
            logger.info(
                "[RANKING] rerank_coverage: %d/%d evaluated (%.1f%%), %d unevaluated",
                n_reranked, total_candidates,
                geometry_metrics["percent_reranked"], n_unevaluated,
            )

            # 6. Sort by final score with deterministic tie-break.
            scored_candidates.sort(key=lambda x: (-x[1], x[0].doc_id))

            # 7. Deduplication
            ranked_candidates = [c for c, _, _ in scored_candidates]
            ranked_candidates = self.deduplicator.deduplicate(ranked_candidates)
            concentration_pre = self._compute_file_concentration_metrics(
                ranked_candidates,
                self.config.concentration_top_k,
            )
            concentration_post = dict(concentration_pre)

            # Rebuild traces in ranked order
            trace_map = {c.doc_id: t for c, _, t in scored_candidates}
            debug_traces = tuple(
                trace_map[c.doc_id] for c in ranked_candidates if c.doc_id in trace_map
            )

            set_opt_metrics = None
            if self.config.set_opt_enabled:
                scores = [s for _, s, _ in scored_candidates]
                score_max = max(scores) if scores else 1.0
                score_min = min(scores) if scores else 0.0
                denom = score_max - score_min if score_max > score_min else 1.0
                relevance_map = {
                    c.doc_id: (s - score_min) / denom
                    for c, s, _ in scored_candidates
                }
                weights = SetObjectiveWeights(
                    relevance=self.config.set_opt_w_relevance,
                    structural_coherence=self.config.set_opt_w_structural,
                    coverage=self.config.set_opt_w_coverage,
                    redundancy=self.config.set_opt_w_redundancy,
                    dispersion=self.config.set_opt_w_dispersion,
                )
                optimizer = SetOptimizer(
                    token_budget=self.config.set_opt_token_budget,
                    weights=weights,
                    callgraph=self.callgraph,
                    concentration_top_k=self.config.concentration_top_k,
                )
                selected, set_opt_metrics = optimizer.select(
                    ranked_candidates,
                    relevance_map=relevance_map,
                    query_concepts=query_concepts,
                )
                ranked_candidates = selected
                concentration_post = self._compute_file_concentration_metrics(
                    ranked_candidates,
                    self.config.concentration_top_k,
                )
                debug_traces = tuple(
                    trace_map[c.doc_id]
                    for c in ranked_candidates
                    if c.doc_id in trace_map
                )
            else:
                # Phase 2: MMR selection
                if self.config.phase2_enabled and self.config.mmr_enabled:
                    relevance_map = {c.doc_id: s for c, s, _ in scored_candidates}
                    lambda_value = self.config.mmr_lambda
                    if profile and self.config.adaptive_weights_enabled:
                        if profile.file_entropy > 0.7:
                            lambda_value = 0.5
                        elif profile.file_entropy >= 0.4:
                            lambda_value = 0.7
                        else:
                            lambda_value = 0.9
                    selected = select_mmr(
                        ranked_candidates,
                        max_items=self.config.mmr_top_n,
                        lambda_value=lambda_value,
                        relevance_map=relevance_map,
                    )
                    ranked_candidates = selected
                    concentration_post = self._compute_file_concentration_metrics(
                        ranked_candidates,
                        self.config.concentration_top_k,
                    )
                    debug_traces = tuple(
                        trace_map[c.doc_id]
                        for c in ranked_candidates
                        if c.doc_id in trace_map
                    )

            # Compute metadata
            latency_ms = int((time.time() - start_time) * 1000)
            metadata = RankMetadata(
                latency_ms=latency_ms,
                reranker_used=reranker_used,
                reranker_unavailable=reranker_unavailable,
                candidate_count=len(ranked_candidates),
                set_optimization=set_opt_metrics.__dict__ if set_opt_metrics else None,
                signal_profile=profile.__dict__ if profile else None,
                ranking_concentration={
                    "top_k": concentration_pre["top_k"],
                    "topK_unique_file_count": concentration_pre["topK_unique_file_count"],
                    "topK_file_entropy": concentration_pre["topK_file_entropy"],
                    "max_file_block_ratio": concentration_pre["max_file_block_ratio"],
                    "pre_selection": concentration_pre,
                    "post_selection": concentration_post,
                },
                ranking_geometry=geometry_metrics,
            )

            return RankingOutput(
                ranked_candidates=tuple(ranked_candidates),
                debug_traces=debug_traces,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Ranking pipeline failed: {e}")
            # Return empty output on error
            return RankingOutput(
                ranked_candidates=tuple(),
                debug_traces=tuple(),
                metadata=RankMetadata(
                    latency_ms=0,
                    reranker_used=False,
                    reranker_unavailable=True,
                    candidate_count=0,
                ),
            )

    @staticmethod
    def _variance(values: list[float]) -> float:
        if not values:
            return 0.0
        mean = sum(values) / float(len(values))
        return sum((v - mean) ** 2 for v in values) / float(len(values))

    @classmethod
    def _compute_geometry_metrics(
        cls,
        scored_candidates,
        reranked_doc_ids: set[str],
        rerank_mean: float,
        rerank_std: float,
        alpha: float,
    ) -> dict[str, float]:
        if not scored_candidates:
            return {
                "alpha_value": float(alpha),
                "rerank_mean": float(rerank_mean),
                "rerank_std": float(rerank_std),
                "rerank_delta_min": 0.0,
                "rerank_delta_max": 0.0,
                "base_variance": 0.0,
                "rerank_variance": 0.0,
                "rerank_delta_variance": 0.0,
                "final_score_variance": 0.0,
                "mean_abs_alpha_rerank_delta": 0.0,
                "rerank_delta_variance_contribution_percent": 0.0,
                "rerank_contribution_percent": 0.0,
            }

        base_values: list[float] = []
        rerank_values_subset: list[float] = []
        rerank_delta_subset: list[float] = []
        alpha_delta_all: list[float] = []
        final_values: list[float] = []

        for candidate, final_score, trace in scored_candidates:
            base_values.append(float(trace.base_score))
            final_values.append(float(final_score))
            if candidate.doc_id in reranked_doc_ids:
                rerank_values_subset.append(float(trace.rerank_score))
                rerank_delta = float(trace.rerank_score) - float(rerank_mean)
                rerank_delta_subset.append(rerank_delta)
                alpha_delta_all.append(float(alpha) * rerank_delta)
            else:
                alpha_delta_all.append(0.0)

        base_variance = cls._variance(base_values)
        rerank_variance = cls._variance(rerank_values_subset)
        rerank_delta_variance = cls._variance(rerank_delta_subset)
        final_variance = cls._variance(final_values)
        alpha_delta_variance = cls._variance(alpha_delta_all)
        rerank_delta_min = min(rerank_delta_subset) if rerank_delta_subset else 0.0
        rerank_delta_max = max(rerank_delta_subset) if rerank_delta_subset else 0.0
        mean_abs_alpha_rerank_delta = (
            sum(abs(v) for v in alpha_delta_all) / float(len(alpha_delta_all))
            if alpha_delta_all
            else 0.0
        )
        rerank_contribution_percent = (
            (alpha_delta_variance / final_variance) * 100.0
            if final_variance > 0.0
            else 0.0
        )

        return {
            "alpha_value": float(alpha),
            "rerank_mean": float(rerank_mean),
            "rerank_std": float(rerank_std),
            "rerank_delta_min": float(rerank_delta_min),
            "rerank_delta_max": float(rerank_delta_max),
            "base_variance": float(base_variance),
            "rerank_variance": float(rerank_variance),
            "rerank_delta_variance": float(rerank_delta_variance),
            "final_score_variance": float(final_variance),
            "mean_abs_alpha_rerank_delta": float(mean_abs_alpha_rerank_delta),
            "rerank_delta_variance_contribution_percent": float(rerank_contribution_percent),
            "rerank_contribution_percent": float(rerank_contribution_percent),
        }

    @staticmethod
    def _compute_file_concentration_metrics(
        candidates,
        top_k: int,
    ) -> dict[str, float | int]:
        if not candidates:
            return {
                "top_k": 0,
                "topK_unique_file_count": 0,
                "topK_file_entropy": 0.0,
                "max_file_block_ratio": 0.0,
            }

        k = min(max(int(top_k), 1), len(candidates))
        top = list(candidates[:k])
        files = [str(c.file) for c in top if getattr(c, "file", None)]
        if not files:
            return {
                "top_k": k,
                "topK_unique_file_count": 0,
                "topK_file_entropy": 0.0,
                "max_file_block_ratio": 0.0,
            }

        counts = Counter(files)
        unique_files = len(counts)
        max_file_block_ratio = max(counts.values()) / float(k)
        if unique_files <= 1:
            entropy = 0.0
        else:
            probs = [cnt / float(k) for cnt in counts.values()]
            raw_entropy = -sum(p * math.log(p) for p in probs if p > 0.0)
            entropy = raw_entropy / math.log(float(unique_files))

        return {
            "top_k": k,
            "topK_unique_file_count": unique_files,
            "topK_file_entropy": entropy,
            "max_file_block_ratio": max_file_block_ratio,
        }
