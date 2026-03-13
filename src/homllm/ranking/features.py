"""Feature enrichment implementation."""

import logging
import re
from typing import Optional

from homllm.ranking.interfaces import FeatureVector
from homllm.ranking.graph_proximity import GraphProximity
from homllm.retrieval.interfaces import Candidate

logger = logging.getLogger(__name__)

_BROAD_SCOPE_MARKERS = {
    "system",
    "across",
    "lifecycle",
    "expected",
    "outcomes",
    "end",
    "stress",
}
_BROAD_BEHAVIOR_MARKERS = {
    "handle",
    "handles",
    "happens",
    "combine",
    "combines",
    "interact",
    "interacts",
    "fallback",
    "fallbacks",
    "flow",
    "summary",
    "summarize",
}
_QUERY_STOPWORDS = {
    "the",
    "and",
    "when",
    "what",
    "how",
    "does",
    "with",
    "into",
    "from",
    "that",
    "this",
    "then",
    "they",
    "them",
    "their",
    "which",
    "where",
    "while",
    "under",
    "over",
    "more",
    "less",
    "than",
    "have",
    "has",
    "had",
    "are",
    "all",
    "can",
    "could",
    "should",
    "would",
    "your",
}
_ARCHITECTURE_TERMS = {
    "adapter",
    "adapters",
    "engine",
    "executor",
    "execution",
    "worker",
    "processor",
    "handler",
    "controller",
    "service",
    "client",
    "queue",
    "pipeline",
    "route",
    "routes",
    "repository",
    "store",
}
_UTILITY_TERMS = {
    "helper",
    "internal",
    "util",
    "utils",
    "config",
    "settings",
    "constant",
    "constants",
    "interface",
    "interfaces",
    "types",
    "test",
    "tests",
    "mock",
}


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

        # Extract robust identifier terms (camel/snake/dot/punctuation-aware).
        query_terms = self._tokenize_name_terms(query)
        broad_system_mode = self._is_broad_system_query(query)
        central_terms = {
            term
            for term in query_terms
            if len(term) >= 4 and term not in _QUERY_STOPWORDS
        }

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
            broad_positive, broad_negative, public_symbol_hit = (
                self._compute_broad_system_bias(candidate, central_terms, broad_system_mode)
            )

            features[candidate.doc_id] = FeatureVector(
                bm25_percentile=bm25_pct,
                dense_percentile=dense_pct,
                name_match_score=name_match,
                is_entrypoint=is_entrypoint,
                has_decorator=has_decorator,
                callgraph_distance=callgraph_dist,
                broad_system_positive=broad_positive,
                broad_system_negative=broad_negative,
                public_symbol_hit=public_symbol_hit,
            )

        return features

    def get_distance_map(self, candidates: list[Candidate]) -> dict[str, int]:
        return self.graph_proximity.compute_distance_map(candidates)

    def _compute_name_match(
        self, candidate: Candidate, query_terms: set[str]
    ) -> float:
        """Compute name match score between candidate and query.

        Prefers candidate.symbol_name (qualified: ClassName_method) when set.
        Falls back to parsing symbol_id (file_id:name:line) for name part.
        Splits by '_', '.', and camel-case boundaries to get overlap terms.
        """
        symbol_name = None
        if candidate.symbol_name:
            symbol_name = candidate.symbol_name
        elif candidate.symbol_id:
            # Parser format: file_id:name:line — use middle part (name)
            parts = candidate.symbol_id.split(":")
            symbol_name = parts[1] if len(parts) >= 2 else candidate.symbol_id
        if not symbol_name:
            return 0.0

        symbol_terms = self._tokenize_name_terms(symbol_name)

        if not query_terms or not symbol_terms:
            return 0.0

        overlap = len(query_terms & symbol_terms)
        return overlap / max(len(query_terms), len(symbol_terms))

    @staticmethod
    def _tokenize_name_terms(text: str) -> set[str]:
        """
        Tokenize text for identifier overlap.

        Handles:
        - snake_case and dotted paths
        - CamelCase / PascalCase
        - punctuation-heavy query text
        - preserves whole token and sub-tokens (e.g. QueryOptimizer -> queryoptimizer, query, optimizer)
        """
        if not text:
            return set()

        # Keep only identifier-like runs, then split structurally.
        identifier_runs = re.findall(r"[A-Za-z0-9_.]+", text)
        if not identifier_runs:
            return set()

        tokens: set[str] = set()
        camel_parts_pattern = re.compile(
            r"[A-Z]+(?=[A-Z][a-z]|[0-9]|\b)|[A-Z]?[a-z]+|[0-9]+"
        )

        for run in identifier_runs:
            for part in run.replace(".", "_").split("_"):
                part = part.strip()
                if not part:
                    continue

                # Whole token preserves exact identifier matching (e.g., connectionpool).
                tokens.add(part.lower())

                # Sub-token support for camel/pascal mixed naming.
                for sub in camel_parts_pattern.findall(part):
                    sub = sub.strip()
                    if sub:
                        tokens.add(sub.lower())

        return tokens

    def _is_entrypoint(self, candidate: Candidate) -> bool:
        """Check if candidate is an entry point (e.g., main function)."""
        if not candidate.symbol_id:
            return False

        # Check if symbol name suggests entry point
        symbol_name = candidate.symbol_id.split(":")[-1] if ":" in candidate.symbol_id else candidate.symbol_id
        entrypoint_names = {"main", "run", "start", "entry", "init"}
        return symbol_name.lower() in entrypoint_names

    def _is_broad_system_query(self, query: str) -> bool:
        query_terms = self._tokenize_name_terms(query)
        scope_hits = len(query_terms & _BROAD_SCOPE_MARKERS)
        behavior_hits = len(query_terms & _BROAD_BEHAVIOR_MARKERS)
        return (scope_hits >= 1 and behavior_hits >= 1) or (
            behavior_hits >= 2 and len(query_terms) >= 8
        )

    def _compute_broad_system_bias(
        self,
        candidate: Candidate,
        central_terms: set[str],
        broad_system_mode: bool,
    ) -> tuple[float, float, bool]:
        if not broad_system_mode:
            return 0.0, 0.0, False

        symbol_name = candidate.symbol_name or ""
        file_path = candidate.file or ""
        path_terms = self._tokenize_name_terms(f"{file_path} {symbol_name}")
        overlap = len(path_terms & central_terms) > 0 if central_terms else False

        public_symbol_hit = bool(symbol_name and not symbol_name.split(".")[-1].startswith("_"))
        private_symbol_hit = bool(symbol_name and symbol_name.split(".")[-1].startswith("_"))
        architecture_hit = len(path_terms & _ARCHITECTURE_TERMS) > 0
        utility_hit = len(path_terms & _UTILITY_TERMS) > 0
        init_only = "__init__" in file_path.replace("\\", "/").lower()

        positive = 0.0
        negative = 0.0

        if public_symbol_hit:
            positive += 0.35
        if architecture_hit:
            positive += 0.40
        if overlap:
            positive += 0.25

        if private_symbol_hit:
            negative += 0.45
        if utility_hit and not overlap:
            negative += 0.35
        if init_only and not overlap:
            negative += 0.20

        return min(1.0, positive), min(1.0, negative), public_symbol_hit

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
