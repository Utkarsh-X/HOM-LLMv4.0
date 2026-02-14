"""Ranking pipeline orchestrator."""

import logging
import time
from typing import Optional

from homllm.ranking.dedup_structural import StructuralDeduplicator
from homllm.ranking.confidence import (
    compute_bm25_vector_disagreement,
    compute_score_entropy,
    compute_score_margin,
)
from homllm.ranking.adaptive_weights import compute_adaptive_weights
from homllm.ranking.features import FeatureEnricher
from homllm.ranking.fusion import ScoreFusion
from homllm.ranking.graph_propagation import NeighborBoosting
from homllm.ranking.interfaces import (
    DebugTrace,
    FeatureVector,
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
            QwenReranker(config.reranker_model) if config.reranker_enabled else None
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
            reranker_used = False
            reranker_unavailable = False
            fire_reranker = True

            if self.config.reranker_enabled and self.reranker:
                if self.config.reranker_gating_enabled:
                    ranked_for_conf = sorted(
                        candidates,
                        key=lambda c: base_scores.get(c.doc_id, 0.0),
                        reverse=True,
                    )
                    top_k = self.config.reranker_gating_top_k
                    scores_for_conf = [
                        base_scores.get(c.doc_id, 0.0)
                        for c in ranked_for_conf[:top_k]
                    ]
                    margin = compute_score_margin(scores_for_conf)
                    entropy = compute_score_entropy(scores_for_conf)
                    disagreement = compute_bm25_vector_disagreement(
                        ranked_for_conf, top_k=top_k
                    )
                    fire_reranker = (
                        len(scores_for_conf)
                        >= self.config.reranker_gating_min_candidates
                        and (
                            margin < self.config.reranker_margin_threshold
                            or entropy > self.config.reranker_entropy_threshold
                            or disagreement
                            > self.config.reranker_disagreement_threshold
                        )
                    )
                    logger.debug(
                        "Reranker gating margin=%.3f entropy=%.3f disagreement=%.3f fire=%s",
                        margin,
                        entropy,
                        disagreement,
                        fire_reranker,
                    )

            if self.config.reranker_enabled and self.reranker and fire_reranker:
                if self.reranker.healthcheck():
                    try:
                        # Get top M candidates for reranking
                        top_m = min(self.config.reranker_top_m, len(candidates))
                        top_candidates = sorted(
                            candidates,
                            key=lambda c: base_scores.get(c.doc_id, 0.0),
                            reverse=True,
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
                        rerank_duration_ms = (time.perf_counter() - rerank_start) * 1000
                        print(f"[RERANK_PHASE] candidates_reranked={len(documents)} duration_ms={rerank_duration_ms:.1f}", flush=True)

                        # Map scores back to candidates
                        for candidate, score in zip(top_candidates, scores):
                            rerank_scores[candidate.doc_id] = score

                        reranker_used = True

                    except Exception as e:
                        logger.error(f"Reranker failed: {e}")
                        reranker_unavailable = True
                else:
                    reranker_unavailable = True
                    logger.warning("Reranker enabled but healthcheck failed.")
            else:
                reranker_unavailable = not self.config.reranker_enabled
                if self.config.reranker_enabled and not fire_reranker:
                    logger.info("Reranker gated off for this query.")

            profile = None
            if self.config.phase2_enabled:
                profile = compute_signal_profile(candidates, base_scores, distance_map)

            if self.config.phase2_enabled and self.config.adaptive_weights_enabled and profile:
                weight_profile = compute_adaptive_weights(
                    self.config.w_base,
                    self.config.w_struct,
                    self.config.w_rerank,
                    profile,
                    reranker_used,
                )
                w_base = weight_profile.w_base
                w_struct = weight_profile.w_struct
                w_rerank = weight_profile.w_rerank
            else:
                w_base = self.config.w_base
                w_struct = self.config.w_struct
                w_rerank = self.config.w_rerank if reranker_used else 0.0

            # 5. Final fusion
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

                final_score = (
                    w_base * base_score
                    + w_rerank * rerank_score
                    + w_struct * struct_bonus
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
                scored_candidates.sort(key=lambda x: x[1], reverse=True)
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
                        w_base * trace.base_score
                        + w_rerank * trace.rerank_score
                        + w_struct * struct_bonus
                    )
                    trace = DebugTrace(
                        candidate_id=trace.candidate_id,
                        base_score=trace.base_score,
                        rerank_score=trace.rerank_score,
                        struct_bonus=struct_bonus,
                        final_score=final_score,
                        features=trace.features,
                        provenance=trace.provenance,
                    )
                    rescored.append((candidate, final_score, trace))

                scored_candidates = rescored

            # 6. Sort by final score
            scored_candidates.sort(key=lambda x: x[1], reverse=True)

            # 7. Deduplication
            ranked_candidates = [c for c, _, _ in scored_candidates]
            ranked_candidates = self.deduplicator.deduplicate(ranked_candidates)

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
                )
                selected, set_opt_metrics = optimizer.select(
                    ranked_candidates,
                    relevance_map=relevance_map,
                    query_concepts=query_concepts,
                )
                ranked_candidates = selected
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
