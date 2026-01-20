"""Protocols and interfaces for Ranking layer."""

from dataclasses import dataclass
from typing import Protocol

from homllm.retrieval.interfaces import Candidate


@dataclass(frozen=True)
class FeatureVector:
    """Feature vector for a candidate."""

    bm25_percentile: float
    dense_percentile: float
    name_match_score: float
    is_entrypoint: bool
    has_decorator: bool
    callgraph_distance: float  # Inverse distance, 0 if not connected


@dataclass(frozen=True)
class DebugTrace:
    """Debug trace for a ranked candidate."""

    candidate_id: str
    base_score: float
    rerank_score: float
    struct_bonus: float
    final_score: float
    features: FeatureVector | None
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class RankMetadata:
    """Metadata for ranking operation."""

    latency_ms: int
    reranker_used: bool
    reranker_unavailable: bool
    candidate_count: int


@dataclass(frozen=True)
class RankingInput:
    """Input to ranking pipeline."""

    query: str
    candidates: tuple[Candidate, ...]  # Immutable
    config: "RankConfig"


@dataclass(frozen=True)
class RankingOutput:
    """Output from ranking pipeline."""

    ranked_candidates: tuple[Candidate, ...]  # Sorted by final_score
    debug_traces: tuple[DebugTrace, ...]
    metadata: RankMetadata


@dataclass
class RankConfig:
    """Ranking layer configuration."""

    reranker_enabled: bool
    reranker_model: str
    reranker_top_m: int
    w_base: float
    w_rerank: float
    w_struct: float
    w_bm25: float
    w_dense: float
    w_name: float
    # Structural bonus weights (all from config, no hardcoded values)
    struct_entrypoint_bonus: float = 0.1
    struct_decorator_bonus: float = 0.05
    struct_callgraph_bonus: float = 0.05
    struct_bonus_cap: float = 0.2


class Reranker(Protocol):
    """Protocol for cross-encoder reranking."""

    def batch_score(self, query: str, documents: list[str]) -> list[float]:
        """
        Cross-encoder scoring. No text synthesis.
        
        Properties:
        - Deterministic
        - No hallucination (scores, not generates)
        - Batch-optimized
        """
        ...

    def healthcheck(self) -> bool:
        """Check if reranker is available."""
        ...
