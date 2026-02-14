"""Feature enrichment implementation."""

import logging
from typing import Optional

from homllm.ranking.interfaces import FeatureVector
from homllm.ranking.graph_proximity import GraphProximity
from homllm.retrieval.interfaces import Candidate

logger = logging.getLogger(__name__)


class FeatureEnricher:
    """Computes feature vectors for candidates."""

    def __init__(
        self,
        callgraph: Optional[dict] = None,
        graph_max_depth: int = 4,
        graph_anchor_k: int = 5,
    ):
        """
        Initialize feature enricher.
        
        Args:
            callgraph: Call graph for structural features (optional)
        """
        self.callgraph = callgraph or {}
        self.graph_proximity = GraphProximity(
            self.callgraph, max_depth=graph_max_depth, anchor_k=graph_anchor_k
        )

    def enrich(
        self, candidates: list[Candidate], query: str
    ) -> dict[str, FeatureVector]:
        """
        Compute feature vectors for all candidates.
        
        Features:
        - bm25_percentile: Normalized BM25 score
        - dense_percentile: Normalized vector score
        - name_match_score: Identifier overlap with query
        - is_entrypoint: Whether symbol is an entry point
        - has_decorator: Whether symbol has decorators
        - callgraph_distance: Inverse distance from seed candidates
        """
        if not candidates:
            return {}

        # Compute percentiles for normalization
        bm25_scores = [c.bm25_score for c in candidates if c.bm25_score > 0]
        dense_scores = [c.vector_score for c in candidates if c.vector_score > 0]

        bm25_max = max(bm25_scores) if bm25_scores else 1.0
        dense_max = max(dense_scores) if dense_scores else 1.0

        # Extract query terms for name matching
        query_terms = set(query.lower().split())

        features: dict[str, FeatureVector] = {}

        distance_map = self.graph_proximity.compute_distance_map(candidates)

        for candidate in candidates:
            # Normalize scores to percentiles
            bm25_pct = (
                candidate.bm25_score / bm25_max if bm25_max > 0 else 0.0
            )
            dense_pct = (
                candidate.vector_score / dense_max if dense_max > 0 else 0.0
            )

            # Name match score
            name_match = self._compute_name_match(candidate, query_terms)

            # Structural features
            is_entrypoint = self._is_entrypoint(candidate)
            has_decorator = self._has_decorator(candidate)

            # Callgraph distance (inverse, 0 if not connected)
            distance = (
                distance_map.get(candidate.symbol_id)
                if candidate.symbol_id
                else None
            )
            callgraph_dist = self.graph_proximity.distance_to_score(distance)

            features[candidate.doc_id] = FeatureVector(
                bm25_percentile=bm25_pct,
                dense_percentile=dense_pct,
                name_match_score=name_match,
                is_entrypoint=is_entrypoint,
                has_decorator=has_decorator,
                callgraph_distance=callgraph_dist,
            )

        return features

    def get_distance_map(self, candidates: list[Candidate]) -> dict[str, int]:
        return self.graph_proximity.compute_distance_map(candidates)

    def _compute_name_match(
        self, candidate: Candidate, query_terms: set[str]
    ) -> float:
        """Compute name match score between candidate and query."""
        if not candidate.symbol_id:
            return 0.0

        # Extract symbol name from doc_id or symbol_id
        # Format: file_id:symbol_id or symbol name
        symbol_name = candidate.symbol_id.split(":")[-1] if ":" in candidate.symbol_id else candidate.symbol_id
        symbol_terms = set(symbol_name.lower().split("_"))

        # Compute overlap
        if not query_terms or not symbol_terms:
            return 0.0

        overlap = len(query_terms & symbol_terms)
        return overlap / max(len(query_terms), len(symbol_terms))

    def _is_entrypoint(self, candidate: Candidate) -> bool:
        """Check if candidate is an entry point (e.g., main function)."""
        if not candidate.symbol_id:
            return False

        # Check if symbol name suggests entry point
        symbol_name = candidate.symbol_id.split(":")[-1] if ":" in candidate.symbol_id else candidate.symbol_id
        entrypoint_names = {"main", "run", "start", "entry", "init"}
        return symbol_name.lower() in entrypoint_names

    def _has_decorator(self, candidate: Candidate) -> bool:
        """Check if candidate has decorators."""
        # Check provenance for decorator expansion
        return "expansion:decorator" in candidate.provenance

    def _compute_callgraph_distance(self, candidate: Candidate) -> float:
        """Deprecated: retained for compatibility."""
        if not self.callgraph or not candidate.symbol_id:
            return 0.0
        if candidate.symbol_id in self.callgraph:
            return 1.0
        return 0.0
