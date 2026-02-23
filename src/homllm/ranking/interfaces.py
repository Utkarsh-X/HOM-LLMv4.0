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
    rerank_evaluated: bool = False  # True if reranker actually scored this candidate


@dataclass(frozen=True)
class RankMetadata:
    """Metadata for ranking operation."""

    latency_ms: int
    reranker_used: bool
    reranker_unavailable: bool
    candidate_count: int
    set_optimization: dict | None = None
    signal_profile: dict | None = None
    ranking_concentration: dict | None = None
    ranking_geometry: dict | None = None


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
    reranker_device: str = "auto"
    # Stage 2 geometry controls (fixed, bounded, deterministic)
    rerank_alpha: float = 0.32
    struct_gamma: float = 0.05
    # Structural bonus weights (all from config, no hardcoded values)
    struct_entrypoint_bonus: float = 0.1
    struct_decorator_bonus: float = 0.05
    struct_callgraph_bonus: float = 0.05
    struct_bonus_cap: float = 0.2
    # Graph proximity configuration
    graph_max_depth: int = 4
    graph_anchor_k: int = 5
    # Structural deduplication configuration
    dedup_file_entropy_threshold: float = 0.6
    # Reranker gating configuration
    reranker_gating_enabled: bool = True
    reranker_margin_threshold: float = 0.2
    reranker_entropy_threshold: float = 0.7
    reranker_disagreement_threshold: float = 0.5
    reranker_gating_top_k: int = 50
    reranker_gating_min_candidates: int = 3
    # Phase 2: adaptive weights and two-pass
    phase2_enabled: bool = False
    adaptive_weights_enabled: bool = False
    two_pass_enabled: bool = False
    two_pass_seed_k: int = 20
    two_pass_max_depth: int = 3
    two_pass_decay: float = 0.8
    # Phase 2: MMR selection
    mmr_enabled: bool = False
    mmr_top_n: int = 30
    mmr_lambda: float = 0.7
    # Set optimization (global selection)
    set_opt_enabled: bool = False
    set_opt_token_budget: int = 3200
    set_opt_w_relevance: float = 1.0
    set_opt_w_structural: float = 0.6
    set_opt_w_coverage: float = 0.8
    set_opt_w_redundancy: float = 0.5
    set_opt_w_dispersion: float = 0.4
    concentration_top_k: int = 10


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
