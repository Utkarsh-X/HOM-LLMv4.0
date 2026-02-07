"""Hybrid BM25 + vector fusion implementation.

Extended for Plan B: Retrieval Layer Activation with:
- Diversity-aware MMR post-fusion
"""

import logging
import time
from typing import Optional

from homllm.retrieval.interfaces import Candidate, RetrievalConfig

logger = logging.getLogger(__name__)


class RRFHybridMerger:
    """Reciprocal Rank Fusion hybrid merger.
    
    Plan B: Optionally applies MMR post-fusion for diversity.
    """
    
    def __init__(self, embedder: Optional[object] = None):
        """
        Initialize merger.
        
        Args:
            embedder: Embedder for MMR similarity computation (optional)
        """
        self.embedder = embedder
        self.last_metrics: dict[str, float | int | str] = {}

    def merge(
        self,
        bm25_results: list[Candidate],
        vector_results: list[Candidate],
        config: RetrievalConfig,
        apply_mmr: bool = True,
    ) -> list[Candidate]:
        """
        Uses Reciprocal Rank Fusion or configurable fusion.
        All weights from config. No magic constants.
        
        Plan B: Applies MMR post-fusion if enabled.
        """
        self.last_metrics = {}
        if config.hybrid_method == "rrf":
            merged = self._rrf_merge(bm25_results, vector_results, config.rrf_k)
        elif config.hybrid_method == "linear":
            merged = self._linear_merge(
                bm25_results, vector_results, config.bm25_weight, config.vector_weight
            )
        else:
            logger.warning(f"Unknown hybrid method: {config.hybrid_method}, using RRF")
            merged = self._rrf_merge(bm25_results, vector_results, config.rrf_k)
        
        # ======================================================================
        # Plan B: Apply MMR post-fusion for diversity
        # ======================================================================
        if (
            apply_mmr
            and config.plan_b_enabled
            and config.diversity_mmr_enabled
            and self.embedder is not None
        ):
            merged = self._apply_mmr(merged, config)
        
        return merged

    def apply_mmr(
        self,
        candidates: list[Candidate],
        config: RetrievalConfig,
    ) -> list[Candidate]:
        if not candidates:
            return candidates
        if not (
            config.plan_b_enabled
            and config.diversity_mmr_enabled
            and self.embedder is not None
        ):
            return candidates
        return self._apply_mmr(candidates, config)
    
    def _apply_mmr(
        self,
        candidates: list[Candidate],
        config: RetrievalConfig,
    ) -> list[Candidate]:
        """Apply deterministic MMR post-fusion."""
        try:
            from homllm.retrieval.diversity_mmr import apply_mmr, compute_candidate_embeddings
            
            # Compute embeddings for candidates
            emb_start = time.perf_counter()
            embeddings = compute_candidate_embeddings(candidates, self.embedder)
            emb_ms = (time.perf_counter() - emb_start) * 1000
            
            if not embeddings:
                logger.debug("MMR: No embeddings computed, skipping")
                return candidates
            
            # Apply MMR
            mmr_start = time.perf_counter()
            result = apply_mmr(
                candidates,
                embeddings,
                mmr_lambda=config.mmr_lambda,
                similarity_threshold=config.mmr_similarity_threshold,
            )
            mmr_ms = (time.perf_counter() - mmr_start) * 1000
            self.last_metrics = {
                "mmr_candidates": len(candidates),
                "mmr_emb_ms": round(emb_ms, 2),
                "mmr_ms": round(mmr_ms, 2),
            }
            logger.info(
                "[MMR_PROFILE] candidates=%d emb_ms=%.1f mmr_ms=%.1f",
                len(candidates),
                emb_ms,
                mmr_ms,
            )
            return result
        except Exception as e:
            self.last_metrics = {"mmr_error": str(e)}
            logger.warning(f"MMR failed, returning original candidates: {e}")
            return candidates

    def _rrf_merge(
        self, bm25_results: list[Candidate], vector_results: list[Candidate], k: int
    ) -> list[Candidate]:
        """
        Reciprocal Rank Fusion.
        
        RRF score = sum(1 / (k + rank)) for each result list
        """
        # Build doc_id -> candidate mapping
        candidates_by_id: dict[str, Candidate] = {}

        # Add BM25 results with ranks
        for rank, candidate in enumerate(bm25_results, start=1):
            if candidate.doc_id not in candidates_by_id:
                candidates_by_id[candidate.doc_id] = candidate
            # Add RRF score contribution
            rrf_score = 1.0 / (k + rank)
            existing = candidates_by_id[candidate.doc_id]
            candidates_by_id[candidate.doc_id] = Candidate(
                doc_id=existing.doc_id,
                file=existing.file,
                symbol_id=existing.symbol_id,
                content=existing.content,
                bm25_score=existing.bm25_score,
                vector_score=existing.vector_score,
                hybrid_score=existing.hybrid_score + rrf_score,
                provenance=existing.provenance,
                granularity_level=existing.granularity_level,
            )

        # Add vector results with ranks
        for rank, candidate in enumerate(vector_results, start=1):
            rrf_score = 1.0 / (k + rank)
            if candidate.doc_id not in candidates_by_id:
                candidates_by_id[candidate.doc_id] = candidate
            existing = candidates_by_id[candidate.doc_id]
            candidates_by_id[candidate.doc_id] = Candidate(
                doc_id=existing.doc_id,
                file=existing.file,
                symbol_id=existing.symbol_id,
                content=existing.content,
                bm25_score=existing.bm25_score,
                vector_score=existing.vector_score,
                hybrid_score=existing.hybrid_score + rrf_score,
                provenance=existing.provenance,
                granularity_level=existing.granularity_level,
            )

        # Sort by hybrid score descending
        merged = list(candidates_by_id.values())
        merged.sort(key=lambda c: c.hybrid_score, reverse=True)

        return merged

    def _linear_merge(
        self,
        bm25_results: list[Candidate],
        vector_results: list[Candidate],
        bm25_weight: float,
        vector_weight: float,
    ) -> list[Candidate]:
        """
        Linear weighted fusion.
        
        Normalize scores to [0, 1] then combine with weights.
        """
        # Normalize BM25 scores
        if bm25_results:
            max_bm25 = max(c.bm25_score for c in bm25_results) or 1.0
            bm25_normalized = {
                c.doc_id: c.bm25_score / max_bm25 for c in bm25_results
            }
        else:
            bm25_normalized = {}

        # Normalize vector scores
        if vector_results:
            max_vector = max(c.vector_score for c in vector_results) or 1.0
            vector_normalized = {
                c.doc_id: c.vector_score / max_vector for c in vector_results
            }
        else:
            vector_normalized = {}

        # Combine all candidates
        candidates_by_id: dict[str, Candidate] = {}

        # Add BM25 candidates
        for candidate in bm25_results:
            norm_score = bm25_normalized.get(candidate.doc_id, 0.0)
            candidates_by_id[candidate.doc_id] = Candidate(
                doc_id=candidate.doc_id,
                file=candidate.file,
                symbol_id=candidate.symbol_id,
                content=candidate.content,
                bm25_score=candidate.bm25_score,
                vector_score=0.0,
                hybrid_score=norm_score * bm25_weight,
                provenance=candidate.provenance,
                granularity_level=candidate.granularity_level,
            )

        # Add/update with vector candidates
        for candidate in vector_results:
            norm_score = vector_normalized.get(candidate.doc_id, 0.0)
            if candidate.doc_id in candidates_by_id:
                existing = candidates_by_id[candidate.doc_id]
                candidates_by_id[candidate.doc_id] = Candidate(
                    doc_id=existing.doc_id,
                    file=existing.file,
                    symbol_id=existing.symbol_id,
                    content=existing.content,
                    bm25_score=existing.bm25_score,
                    vector_score=candidate.vector_score,
                    hybrid_score=existing.hybrid_score + (norm_score * vector_weight),
                    provenance=existing.provenance + candidate.provenance,
                    granularity_level=existing.granularity_level or candidate.granularity_level,
                )
            else:
                candidates_by_id[candidate.doc_id] = Candidate(
                    doc_id=candidate.doc_id,
                    file=candidate.file,
                    symbol_id=candidate.symbol_id,
                    content=candidate.content,
                    bm25_score=0.0,
                    vector_score=candidate.vector_score,
                    hybrid_score=norm_score * vector_weight,
                    provenance=candidate.provenance,
                    granularity_level=candidate.granularity_level,
                )

        # Sort by hybrid score descending
        merged = list(candidates_by_id.values())
        merged.sort(key=lambda c: c.hybrid_score, reverse=True)

        return merged

