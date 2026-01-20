"""Hybrid BM25 + vector fusion implementation."""

import logging
from typing import Optional

from homllm.retrieval.interfaces import Candidate, HybridMerger, RetrievalConfig

logger = logging.getLogger(__name__)


class RRFHybridMerger(HybridMerger):
    """Reciprocal Rank Fusion hybrid merger."""

    def merge(
        self,
        bm25_results: list[Candidate],
        vector_results: list[Candidate],
        config: RetrievalConfig,
    ) -> list[Candidate]:
        """
        Uses Reciprocal Rank Fusion or configurable fusion.
        All weights from config. No magic constants.
        """
        if config.hybrid_method == "rrf":
            return self._rrf_merge(bm25_results, vector_results, config.rrf_k)
        elif config.hybrid_method == "linear":
            return self._linear_merge(
                bm25_results, vector_results, config.bm25_weight, config.vector_weight
            )
        else:
            logger.warning(f"Unknown hybrid method: {config.hybrid_method}, using RRF")
            return self._rrf_merge(bm25_results, vector_results, config.rrf_k)

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
                )

        # Sort by hybrid score descending
        merged = list(candidates_by_id.values())
        merged.sort(key=lambda c: c.hybrid_score, reverse=True)

        return merged
