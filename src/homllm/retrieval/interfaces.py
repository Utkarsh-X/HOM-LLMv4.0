"""Protocols and interfaces for Retrieval layer.

Extended for Plan B: Retrieval Layer Activation with:
- Diversity-aware MMR post-fusion
- Intent-driven granularity boosting
- Graph-based structural expansion (GRAPH_STITCH)
"""

from dataclasses import dataclass, field
from typing import Optional, Protocol

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
    
    # Plan B: Granularity level for intent-driven boosting
    granularity_level: str | None = None


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
    """Retrieval layer configuration.
    
    Extended for Plan B: Retrieval Layer Activation.
    """

    # Core retrieval settings
    bm25_top_k: int
    vector_top_k: int
    hybrid_method: str  # "rrf" or "linear"
    rrf_k: int
    bm25_weight: float
    vector_weight: float
    expansion_enabled: bool
    expansion_max_additions: int
    expansion_min_similarity: float
    
    # ==========================================================================
    # Plan B: Retrieval Layer Activation
    # ==========================================================================
    
    # Master toggle for Plan B features
    plan_b_enabled: bool = True
    
    # Diversity-aware MMR (post-RRF)
    diversity_mmr_enabled: bool = True
    mmr_lambda: float = 0.6
    mmr_similarity_threshold: float = 0.85
    
    # Intent-driven granularity boosting
    granularity_boost_enabled: bool = True
    granularity_boost_table: dict = field(default_factory=dict)
    
    # Graph-based structural expansion (GRAPH_STITCH)
    graph_stitch_enabled: bool = True
    graph_stitch_max_depth: int = 2
    graph_stitch_max_additions: int = 8
    graph_stitch_min_confidence: float = 0.5
    graph_stitch_relation_priority: list[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Set defaults for Plan B config."""
        if not self.granularity_boost_table:
            self.granularity_boost_table = {
                "EXPLAIN": {"coarse": 2.0, "medium": 1.5, "fine": 1.0},
                "IMPLEMENT": {"fine": 2.0, "medium": 1.2, "coarse": 0.8},
                "REFACTOR": {"fine": 1.8, "medium": 1.5, "coarse": 1.0},
                "DEBUG": {"fine": 2.5, "medium": 1.5, "coarse": 1.0},
                "SEARCH": {"medium": 1.8, "fine": 1.5, "coarse": 1.0},
                "UNKNOWN": {"fine": 1.0, "medium": 1.0, "coarse": 1.0},
            }
        
        if not self.graph_stitch_relation_priority:
            self.graph_stitch_relation_priority = [
                "calls", "overrides", "imports", "uses", "inherits", "type_annotates"
            ]

