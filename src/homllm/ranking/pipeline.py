"""Ranking pipeline orchestrator."""

import logging
import time
from typing import Optional

from homllm.ranking.dedup import Deduplicator
from homllm.ranking.features import FeatureEnricher
from homllm.ranking.fusion import ScoreFusion
from homllm.ranking.interfaces import (
    DebugTrace,
    FeatureVector,
    RankConfig,
    RankMetadata,
    RankingInput,
    RankingOutput,
)
from homllm.ranking.reranker import QwenReranker

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
        self.feature_enricher = FeatureEnricher(callgraph)
        self.fusion = ScoreFusion()
        self.deduplicator = Deduplicator()
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

            # 3. Base fusion
            base_scores: dict[str, float] = {}
            for candidate in candidates:
                candidate_features = features.get(candidate.doc_id)
                if candidate_features:
                    base_scores[candidate.doc_id] = self.fusion.compute_base_score(
                        candidate_features, self.config
                    )

            # 4. Reranker (optional)
            rerank_scores: dict[str, float] = {}
            reranker_used = False
            reranker_unavailable = False

            if self.config.reranker_enabled and self.reranker:
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
            else:
                reranker_unavailable = not self.config.reranker_enabled

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

                final_score = self.fusion.compute_final_score(
                    base_score, rerank_score, struct_bonus, self.config
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

            # Compute metadata
            latency_ms = int((time.time() - start_time) * 1000)
            metadata = RankMetadata(
                latency_ms=latency_ms,
                reranker_used=reranker_used,
                reranker_unavailable=reranker_unavailable,
                candidate_count=len(ranked_candidates),
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
