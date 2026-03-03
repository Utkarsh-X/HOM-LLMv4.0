"""Ranking pipeline orchestrator."""

from collections import Counter
from dataclasses import replace
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
            reranker_top_m_doc_ids: list[str] = []
            reranker_bm25_rescue_doc_ids: list[str] = []
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
                        reranker_top_m_doc_ids = [c.doc_id for c in top_candidates]

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

                        # A3: Secondary pass — rerank high-BM25 candidates that fell outside top-M
                        rescue_k = max(0, self.config.reranker_bm25_rescue_top_k)
                        if rescue_k > 0:
                            bm25_top = sorted(
                                candidates,
                                key=lambda c: (-getattr(c, "bm25_score", 0.0), c.doc_id),
                            )[:rescue_k]
                            rescue_candidates = [
                                c for c in bm25_top
                                if c.doc_id not in reranked_doc_ids
                            ]
                            reranker_bm25_rescue_doc_ids = [
                                c.doc_id for c in rescue_candidates
                            ]
                            if rescue_candidates:
                                rescue_docs = [
                                    c.content if c.content else c.doc_id
                                    for c in rescue_candidates
                                ]
                                rescue_start = time.perf_counter()
                                rescue_scores = self.reranker.batch_score(
                                    input_data.query, rescue_docs
                                )
                                rescue_ms = (time.perf_counter() - rescue_start) * 1000
                                for c, sc in zip(rescue_candidates, rescue_scores):
                                    rerank_scores[c.doc_id] = sc
                                    reranked_doc_ids.add(c.doc_id)
                                print(
                                    f"[RERANK_PHASE] rescue_reranked={len(rescue_candidates)} duration_ms={rescue_ms:.1f}",
                                    flush=True,
                                )

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

            # Use configured additive reranker weight directly (no mean-centering, no hard cap).
            w_rerank = float(self.config.w_rerank)
            w_struct = max(0.0, float(self.config.w_struct))
            effective_config = replace(self.config, w_rerank=w_rerank, w_struct=w_struct)
            rerank_subset = [rerank_scores[doc_id] for doc_id in reranked_doc_ids]
            rerank_mean = 0.0
            rerank_std = 0.0
            if rerank_subset:
                rerank_mean = sum(rerank_subset) / float(len(rerank_subset))
                rerank_std = math.sqrt(self._variance(rerank_subset))

            alpha = w_rerank
            logger.debug(f"RERANKER_FORMULA: additive, alpha={alpha}")

            # 5. Stage 2 geometry: final score via ScoreFusion.compute_final_score
            scored_candidates: list[tuple[Candidate, float, DebugTrace]] = []

            for candidate in candidates:
                candidate_features = features.get(candidate.doc_id)
                if not candidate_features:
                    continue

                base_score = base_scores.get(candidate.doc_id, 0.0)
                rerank_score = rerank_scores.get(candidate.doc_id, 0.0)
                struct_bonus = self.fusion.compute_struct_bonus(
                    candidate_features, self.config
                )

                final_score = self.fusion.compute_final_score(
                    base_score, rerank_score, struct_bonus, effective_config
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

                    final_score = self.fusion.compute_final_score(
                        trace.base_score, trace.rerank_score, struct_bonus, effective_config
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
                alpha=w_rerank,
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

            # D1 verification: log top-5 formula breakdown (hand_rolled vs compute_final_score)
            for i, (c, fs, t) in enumerate(scored_candidates[:5]):
                hand = (
                    effective_config.w_base * t.base_score
                    + w_rerank * t.rerank_score
                    + w_struct * t.struct_bonus
                )
                fusion = self.fusion.compute_final_score(
                    t.base_score, t.rerank_score, t.struct_bonus, effective_config
                )
                logger.debug(
                    "[FORMULA_VERIFY] rank=%d doc_id=%s w_base=%.6f w_rerank=%.6f w_struct=%.6f "
                    "base=%.6f rerank=%.6f struct=%.6f hand=%.6f fusion=%.6f",
                    i + 1,
                    c.doc_id,
                    effective_config.w_base,
                    w_rerank,
                    w_struct,
                    t.base_score,
                    t.rerank_score,
                    t.struct_bonus,
                    hand,
                    fusion,
                )
                if abs(hand - fusion) > 1e-9:
                    logger.warning(
                        "Formula mismatch rank=%d doc_id=%s hand=%.6f fusion=%.6f",
                        i + 1, c.doc_id, hand, fusion,
                    )

            # 7. Deduplication
            ranked_candidates_pre_dedup = [c for c, _, _ in scored_candidates]
            ranked_candidates = list(ranked_candidates_pre_dedup)
            ranked_candidates = self.deduplicator.deduplicate(ranked_candidates)
            dedup_decisions = list(getattr(self.deduplicator, "last_trace", []) or [])
            dedup_meta = dict(getattr(self.deduplicator, "last_meta", {}) or {})
            concentration_pre = self._compute_file_concentration_metrics(
                ranked_candidates,
                self.config.concentration_top_k,
            )
            concentration_post = dict(concentration_pre)
            ranked_candidates_post_dedup = list(ranked_candidates)

            # Rebuild traces in ranked order
            trace_map = {c.doc_id: t for c, _, t in scored_candidates}
            debug_traces = tuple(
                trace_map[c.doc_id] for c in ranked_candidates if c.doc_id in trace_map
            )

            set_opt_metrics = None
            adaptive_weight_trace: dict[str, object] = {
                "enabled": bool(self.config.set_opt_enabled),
                "applied": False,
            }
            if self.config.set_opt_enabled:
                scores = [s for _, s, _ in scored_candidates]
                score_max = max(scores) if scores else 1.0
                score_min = min(scores) if scores else 0.0
                denom = score_max - score_min if score_max > score_min else 1.0
                relevance_map = {
                    c.doc_id: (s - score_min) / denom
                    for c, s, _ in scored_candidates
                }

                # --- Fix C: Adaptive dispersion ---
                # Detect candidate file concentration after dedup.
                # If one file dominates AND its blocks have above-average
                # reranker confidence, reduce dispersion to allow depth.
                # Initialize to safe defaults before any conditional logic
                # (avoids UnboundLocalError when block is skipped or
                # reranker_blocks_reduction is false).
                adaptive_dispersion = float(self.config.set_opt_w_dispersion)
                adaptive_redundancy = float(self.config.set_opt_w_redundancy)
                DISPERSION_FLOOR = 0.05
                CONCENTRATION_THRESHOLD = 0.40  # 40%+ from one file

                file_counts: dict[str, int] = {}
                for c in ranked_candidates:
                    if c.file:
                        file_counts[c.file] = file_counts.get(c.file, 0) + 1
                total_post_dedup = len(ranked_candidates)
                adaptive_weight_trace.update(
                    {
                        "file_counts_post_dedup": dict(sorted(file_counts.items())),
                        "total_post_dedup": int(total_post_dedup),
                    }
                )

                if total_post_dedup > 0 and file_counts:
                    dominant_file = max(file_counts, key=file_counts.get)
                    dominant_ratio = file_counts[dominant_file] / total_post_dedup
                    adaptive_weight_trace.update(
                        {
                            "dominant_file": dominant_file,
                            "dominant_ratio": float(dominant_ratio),
                            "concentration_threshold": float(CONCENTRATION_THRESHOLD),
                        }
                    )

                    if dominant_ratio >= CONCENTRATION_THRESHOLD:
                        # Check reranker confidence for dominant file's blocks.
                        dominant_rerank_scores = []
                        all_rerank_scores = []
                        for c in ranked_candidates:
                            trace = trace_map.get(c.doc_id)
                            if trace and trace.rerank_evaluated:
                                all_rerank_scores.append(trace.rerank_score)
                                if c.file == dominant_file:
                                    dominant_rerank_scores.append(trace.rerank_score)

                        avg_all = (
                            sum(all_rerank_scores) / len(all_rerank_scores)
                            if all_rerank_scores else 0.0
                        )
                        avg_dominant = (
                            sum(dominant_rerank_scores) / len(dominant_rerank_scores)
                            if dominant_rerank_scores else 0.0
                        )

                        # Gate: reduce dispersion when EITHER:
                        # (a) dominant file blocks have above-average reranker score, OR
                        # (b) dominant file blocks were not reranked (concentration
                        #     signal alone is sufficient — no negative evidence), OR
                        # (c) no blocks were reranked at all.
                        # Only BLOCK reduction when dominant file blocks were
                        # explicitly evaluated AND scored below average.
                        reranker_blocks_reduction = (
                            not dominant_rerank_scores  # not evaluated → no negative evidence
                            or avg_dominant >= avg_all  # evaluated and confident
                            or not all_rerank_scores    # nothing evaluated at all
                        )
                        adaptive_weight_trace.update(
                            {
                                "all_rerank_scores_count": int(len(all_rerank_scores)),
                                "dominant_rerank_scores_count": int(len(dominant_rerank_scores)),
                                "avg_all_rerank": float(avg_all),
                                "avg_dominant_rerank": float(avg_dominant),
                                "reranker_blocks_reduction": bool(reranker_blocks_reduction),
                            }
                        )

                        if reranker_blocks_reduction:
                            # Concentration + confidence → aggressively reduce
                            # dispersion AND redundancy to allow depth from the
                            # dominant file.
                            #
                            # With defaults w_dispersion=0.4 + w_redundancy=0.5,
                            # the combined anti-depth penalty is 0.9.  To allow
                            # implementation blocks to survive, both must drop.
                            adaptive_dispersion = DISPERSION_FLOOR
                            adaptive_redundancy = self.config.set_opt_w_redundancy * 0.5
                            logger.info(
                                "[RANKING] Adaptive dispersion: file=%s "
                                "concentration=%.1f%% reranker_avg=%.3f (all=%.3f) "
                                "w_dispersion %.3f -> %.3f  "
                                "w_redundancy %.3f -> %.3f",
                                dominant_file, dominant_ratio * 100,
                                avg_dominant, avg_all,
                                self.config.set_opt_w_dispersion, adaptive_dispersion,
                                self.config.set_opt_w_redundancy, adaptive_redundancy,
                            )
                            adaptive_weight_trace["applied"] = True
                    else:
                        adaptive_redundancy = None

                if adaptive_redundancy is None:
                    adaptive_redundancy = self.config.set_opt_w_redundancy
                adaptive_weight_trace.update(
                    {
                        "adaptive_dispersion": float(adaptive_dispersion),
                        "adaptive_redundancy": float(adaptive_redundancy),
                    }
                )

                weights = SetObjectiveWeights(
                    relevance=self.config.set_opt_w_relevance,
                    structural_coherence=self.config.set_opt_w_structural,
                    coverage=self.config.set_opt_w_coverage,
                    redundancy=adaptive_redundancy,
                    dispersion=adaptive_dispersion,
                )
                optimizer = SetOptimizer(
                    token_budget=self.config.set_opt_token_budget,
                    weights=weights,
                    callgraph=self.callgraph,
                    concentration_top_k=self.config.concentration_top_k,
                    max_rounds=self.config.set_opt_max_rounds,
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

            ranking_subtrace = self._build_ranking_subtrace(
                query=input_data.query,
                input_candidates=candidates,
                features=features,
                base_scores=base_scores,
                rerank_scores=rerank_scores,
                reranked_doc_ids=reranked_doc_ids,
                reranker_top_m_doc_ids=reranker_top_m_doc_ids,
                reranker_bm25_rescue_doc_ids=reranker_bm25_rescue_doc_ids,
                scored_candidates=scored_candidates,
                ranked_candidates_pre_dedup=ranked_candidates_pre_dedup,
                ranked_candidates_post_dedup=ranked_candidates_post_dedup,
                ranked_candidates_final=ranked_candidates,
                dedup_decisions=dedup_decisions,
                dedup_meta=dedup_meta,
                adaptive_weight_trace=adaptive_weight_trace,
                set_opt_metrics=set_opt_metrics.__dict__ if set_opt_metrics else None,
                effective_config=effective_config,
            )
            ranking_subtrace_summary = self._summarize_ranking_subtrace(ranking_subtrace)

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
                ranking_subtrace_summary=ranking_subtrace_summary,
            )

            return RankingOutput(
                ranked_candidates=tuple(ranked_candidates),
                debug_traces=debug_traces,
                metadata=metadata,
                ranking_subtrace=ranking_subtrace,
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
    def _serialize_candidate(candidate) -> dict[str, object]:
        return {
            "doc_id": candidate.doc_id,
            "file": candidate.file,
            "symbol_id": candidate.symbol_id,
            "parent_symbol_id": candidate.parent_symbol_id,
            "symbol_name": candidate.symbol_name,
            "granularity_level": candidate.granularity_level,
            "span_start": candidate.span_start,
            "span_end": candidate.span_end,
            "bm25_score": float(candidate.bm25_score),
            "vector_score": float(candidate.vector_score),
            "hybrid_score": float(candidate.hybrid_score),
            "provenance": list(candidate.provenance),
            "entity_ids": list(candidate.entity_ids),
            "content": candidate.content,
        }

    def _build_ranking_subtrace(
        self,
        *,
        query: str,
        input_candidates,
        features,
        base_scores,
        rerank_scores,
        reranked_doc_ids,
        reranker_top_m_doc_ids,
        reranker_bm25_rescue_doc_ids,
        scored_candidates,
        ranked_candidates_pre_dedup,
        ranked_candidates_post_dedup,
        ranked_candidates_final,
        dedup_decisions,
        dedup_meta,
        adaptive_weight_trace,
        set_opt_metrics,
        effective_config,
    ) -> dict[str, object]:
        scored_map = {c.doc_id: (c, s, t) for c, s, t in scored_candidates}
        feature_rows = []
        base_rows = []
        final_rows = []
        scored_ids = set()
        for candidate in input_candidates:
            fv = features.get(candidate.doc_id)
            feature_rows.append(
                {
                    "doc_id": candidate.doc_id,
                    "has_feature": fv is not None,
                    "bm25_percentile": float(fv.bm25_percentile) if fv else None,
                    "dense_percentile": float(fv.dense_percentile) if fv else None,
                    "name_match_score": float(fv.name_match_score) if fv else None,
                    "is_entrypoint": bool(fv.is_entrypoint) if fv else False,
                    "has_decorator": bool(fv.has_decorator) if fv else False,
                    "callgraph_distance": float(fv.callgraph_distance) if fv else None,
                }
            )
            if fv is not None:
                base_rows.append(
                    {
                        "doc_id": candidate.doc_id,
                        "bm25_component": float(self.config.w_bm25 * fv.bm25_percentile),
                        "dense_component": float(self.config.w_dense * fv.dense_percentile),
                        "name_component": float(self.config.w_name * fv.name_match_score),
                        "base_score": float(base_scores.get(candidate.doc_id, 0.0)),
                    }
                )
            if candidate.doc_id in scored_map:
                scored_ids.add(candidate.doc_id)
                _, _, trace = scored_map[candidate.doc_id]
                final_rows.append(
                    {
                        "doc_id": candidate.doc_id,
                        "base_score": float(trace.base_score),
                        "rerank_score": float(trace.rerank_score),
                        "struct_bonus": float(trace.struct_bonus),
                        "w_base_component": float(effective_config.w_base * trace.base_score),
                        "w_rerank_component": float(effective_config.w_rerank * trace.rerank_score),
                        "w_struct_component": float(effective_config.w_struct * trace.struct_bonus),
                        "final_score": float(trace.final_score),
                        "rerank_evaluated": bool(trace.rerank_evaluated),
                    }
                )

        post_dedup_ids = {c.doc_id for c in ranked_candidates_post_dedup}
        final_ids = {c.doc_id for c in ranked_candidates_final}

        dedup_eliminated: dict[str, str] = {}
        for decision in dedup_decisions:
            doc_id = decision.get("doc_id")
            action = decision.get("action")
            reason = str(decision.get("reason", "dedup"))
            if not doc_id:
                continue
            if action in {"skip", "drop"}:
                dedup_eliminated[str(doc_id)] = reason
            if action == "replace":
                replaced_one = decision.get("replaced_candidate_id")
                if replaced_one:
                    dedup_eliminated[str(replaced_one)] = reason
                for replaced_many in decision.get("replaced_candidate_ids") or []:
                    dedup_eliminated[str(replaced_many)] = reason

        elimination_ledger = []
        for candidate in input_candidates:
            doc_id = candidate.doc_id
            if doc_id in final_ids:
                continue
            stage = "R4_FINAL_FUSION"
            reason = "not_in_final_ranked_set"
            if doc_id not in features:
                stage = "R1_FEATURE_ENRICHMENT"
                reason = "missing_feature_vector"
            elif doc_id not in scored_ids:
                stage = "R2_BASE_FUSION"
                reason = "missing_base_or_final_score"
            elif doc_id in dedup_eliminated:
                stage = "R5_DEDUP"
                reason = dedup_eliminated[doc_id]
            elif doc_id in post_dedup_ids:
                if set_opt_metrics is not None:
                    stage = "R7_SET_OPTIMIZER"
                    reason = "not_selected_by_set_optimizer"
                elif self.config.phase2_enabled and self.config.mmr_enabled:
                    stage = "R7_SET_OPTIMIZER"
                    reason = "filtered_by_mmr_selection"
            elimination_ledger.append(
                {
                    "doc_id": doc_id,
                    "file": candidate.file,
                    "first_eliminating_subcomponent": stage,
                    "reason_code": reason,
                }
            )

        set_opt_rounds = []
        if isinstance(set_opt_metrics, dict):
            set_opt_rounds = list(set_opt_metrics.get("round_trace") or [])

        return {
            "schema_version": "1.0",
            "query": query,
            "input_surface": [self._serialize_candidate(c) for c in input_candidates],
            "feature_enrichment": feature_rows,
            "base_fusion": base_rows,
            "reranker_selection": {
                "top_m_selected": list(reranker_top_m_doc_ids),
                "bm25_rescue_selected": list(reranker_bm25_rescue_doc_ids),
                "reranked_doc_ids": sorted(str(x) for x in reranked_doc_ids),
                "unreranked_doc_ids": sorted(
                    c.doc_id for c in input_candidates if c.doc_id not in reranked_doc_ids
                ),
                "rerank_scores": {
                    str(k): float(v) for k, v in sorted(rerank_scores.items())
                },
            },
            "final_fusion": final_rows,
            "dedup_decisions": dedup_decisions,
            "dedup_meta": dedup_meta,
            "adaptive_weights": adaptive_weight_trace,
            "set_optimizer_rounds": set_opt_rounds,
            "set_optimizer_summary": set_opt_metrics,
            "final_output_surface": [self._serialize_candidate(c) for c in ranked_candidates_final],
            "elimination_ledger": elimination_ledger,
        }

    @staticmethod
    def _summarize_ranking_subtrace(subtrace: dict[str, object]) -> dict[str, object]:
        elimination = subtrace.get("elimination_ledger") or []
        counts: dict[str, int] = {}
        for entry in elimination:
            stage = str(entry.get("first_eliminating_subcomponent", "UNKNOWN"))
            counts[stage] = counts.get(stage, 0) + 1
        return {
            "schema_version": subtrace.get("schema_version"),
            "input_candidates": len(subtrace.get("input_surface") or []),
            "final_candidates": len(subtrace.get("final_output_surface") or []),
            "elimination_by_subcomponent": counts,
            "dedup_decisions": len(subtrace.get("dedup_decisions") or []),
            "set_optimizer_round_events": len(subtrace.get("set_optimizer_rounds") or []),
        }

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
                # Additive formula: alpha * rerank_score (not delta)
                alpha_delta_all.append(float(alpha) * float(trace.rerank_score))
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
