"""Protocols and interfaces for Retrieval layer."""

from dataclasses import dataclass
from typing import Protocol

from homllm.common.types import Intent, Vector


@dataclass(frozen=True)
class Candidate:
    """Retrieved candidate code block."""

    doc_id: str
    file: str
    symbol_id: str | None
    content: str
    bm25_score: float = 0.0
    vector_score: float = 0.0
    hybrid_score: float = 0.0
    provenance: tuple[str, ...] = ()  # e.g., ("bm25", "expansion:decorator")


@dataclass(frozen=True)
class PreparedQuery:
    """Prepared query for retrieval."""

    dense_query: str  # Instruction-wrapped query for embedding
    lexical_terms: list[str]  # Extracted keywords for BM25
    intent: Intent


@dataclass(frozen=True)
class RetrievalResult:
    """Result of retrieval pipeline."""

    candidates: list[Candidate]
    query_id: str
    metadata: dict


class QueryPreparer(Protocol):
    """Protocol for query preparation."""

    def prepare(self, query: str, intent: Intent) -> PreparedQuery:
        """
        Returns:
            dense_query: Instruction-wrapped query for embedding
            lexical_terms: Extracted keywords for BM25
        """
        ...


class HybridMerger(Protocol):
    """Protocol for hybrid BM25 + vector fusion."""

    def merge(
        self,
        bm25_results: list[Candidate],
        vector_results: list[Candidate],
        config: "RetrievalConfig",
    ) -> list[Candidate]:
        """
        Uses Reciprocal Rank Fusion or configurable fusion.
        All weights from config. No magic constants.
        """
        ...


class StructuralExpander(Protocol):
    """Protocol for structural expansion."""

    def expand(
        self,
        candidates: list[Candidate],
        query: str,
        callgraph: dict,  # Simplified callgraph access
        config: "RetrievalConfig",
    ) -> list[Candidate]:
        """
        Adds structurally related candidates (decorators, callees).
        
        Invariants:
        - max_additions enforced from config
        - Only adds if semantic similarity > min_similarity (from config)
        - Provenance tracked for each addition
        """
        ...


@dataclass
class RetrievalConfig:
    """Retrieval layer configuration."""

    bm25_top_k: int
    vector_top_k: int
    hybrid_method: str  # "rrf" or "linear"
    rrf_k: int
    bm25_weight: float
    vector_weight: float
    expansion_enabled: bool
    expansion_max_additions: int
    expansion_min_similarity: float
