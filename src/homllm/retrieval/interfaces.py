"""Protocols and interfaces for Retrieval layer.

Extended for Plan B: Retrieval Layer Activation with:
- Diversity-aware MMR post-fusion
- Intent-driven granularity boosting
- Graph-based structural expansion (GRAPH_STITCH)
"""

from copy import deepcopy
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
    # Span data for structural ranking/dedup
    span_start: int | None = None
    span_end: int | None = None
    parent_symbol_id: str | None = None
    entity_ids: tuple[str, ...] = ()
    doc_type: str | None = None
    semantic_embedding: tuple[float, ...] | None = None


@dataclass(frozen=True)
class PreparedQuery:
    """Prepared query for retrieval."""

    dense_query: str  # Raw query text for embedding
    lexical_terms: list[str]  # Extracted keywords for BM25
    intent: Intent
    lexical_expansion_terms: tuple[str, ...] = ()


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
            dense_query: Raw query text for embedding
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
    vector_calibration_mode: str = "legacy"  # "legacy" | "calibrated_v1"
    parallel_search_enabled: bool = True
    static_ceiling_experiment_enabled: bool = False
    static_ceiling_branch_multiplier: int = 1
    static_ceiling_post_merge_multiplier: int = 1
    static_ceiling_output_multiplier: int = 1
    precision_recovery_enabled: bool = True
    precision_recovery_max_additions: int = 3
    precision_recovery_max_ratio: float = 0.2
    precision_recovery_scan_candidates: int = 8
    precision_recovery_identifier_limit: int = 16
    precision_recovery_bm25_top_k: int = 5
    precision_recovery_vector_top_k: int = 3
    precision_recovery_min_confidence: float = 0.8
    query_expansion_enabled: bool = True
    query_expansion_max_terms: int = 6
    query_expansion_min_token_length: int = 3
    query_expansion_synonyms: dict = field(default_factory=dict)
    
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
    graph_cache_enabled: bool = True
    graph_stitch_beam_high: int = 8
    graph_stitch_beam_low: int = 3

    # Post-merge candidate cap (applied after hybrid merge)
    post_merge_candidates: int = 0
    
    # Budget-aware candidate selection
    context_budget: int = 4000
    budget_reserve: int = 800
    budget_aware_selection: bool = True
    
    # Granularity mixing
    granularity_mixing_enabled: bool = True
    granularity_mixing_profiles: dict = field(default_factory=dict)
    
    # Hierarchical deduplication
    hierarchical_dedup_enabled: bool = True
    
    def __post_init__(self):
        """Set defaults for Plan B config."""
        self.static_ceiling_branch_multiplier = max(1, int(self.static_ceiling_branch_multiplier))
        self.static_ceiling_post_merge_multiplier = max(1, int(self.static_ceiling_post_merge_multiplier))
        self.static_ceiling_output_multiplier = max(1, int(self.static_ceiling_output_multiplier))
        self.vector_calibration_mode = str(self.vector_calibration_mode).strip().lower()
        if self.vector_calibration_mode not in {"legacy", "calibrated_v1"}:
            raise ValueError(
                "retrieval.vector.calibration_mode must be one of: legacy, calibrated_v1"
            )
        self.precision_recovery_max_additions = max(0, int(self.precision_recovery_max_additions))
        self.precision_recovery_max_ratio = max(0.0, min(0.2, float(self.precision_recovery_max_ratio)))
        self.precision_recovery_scan_candidates = max(1, int(self.precision_recovery_scan_candidates))
        self.precision_recovery_identifier_limit = max(1, int(self.precision_recovery_identifier_limit))
        self.precision_recovery_bm25_top_k = max(1, int(self.precision_recovery_bm25_top_k))
        self.precision_recovery_vector_top_k = max(1, int(self.precision_recovery_vector_top_k))
        self.precision_recovery_min_confidence = max(
            0.0,
            min(1.0, float(self.precision_recovery_min_confidence)),
        )
        self.query_expansion_max_terms = max(0, min(32, int(self.query_expansion_max_terms)))
        self.query_expansion_min_token_length = max(1, int(self.query_expansion_min_token_length))
        self.query_expansion_synonyms = self._normalize_query_expansion_synonyms(
            self.query_expansion_synonyms
        )
        self.context_budget = max(1, int(self.context_budget))
        self.budget_reserve = max(0, int(self.budget_reserve))
        if self.budget_reserve > self.context_budget:
            raise ValueError(
                "retrieval budget_reserve cannot exceed context_budget"
            )

        if not self.granularity_boost_table:
            self.granularity_boost_table = {
                "EXPLAIN": {"coarse": 2.0, "medium": 1.5, "fine": 1.0},
                "IMPLEMENT": {"fine": 2.0, "medium": 1.2, "coarse": 0.8},
                "REFACTOR": {"fine": 1.8, "medium": 1.5, "coarse": 1.0},
                "DEBUG": {"fine": 2.5, "medium": 1.5, "coarse": 1.0},
                "SEARCH": {"medium": 1.8, "fine": 1.5, "coarse": 1.0},
                "UNKNOWN": {"fine": 1.0, "medium": 1.0, "coarse": 1.0},
            }

        # Backward-compatible intent aliases.
        if "EXPLANATORY" not in self.granularity_boost_table and "EXPLAIN" in self.granularity_boost_table:
            self.granularity_boost_table["EXPLANATORY"] = dict(
                self.granularity_boost_table["EXPLAIN"]
            )
        if "IMPLEMENTATION" not in self.granularity_boost_table and "IMPLEMENT" in self.granularity_boost_table:
            self.granularity_boost_table["IMPLEMENTATION"] = dict(
                self.granularity_boost_table["IMPLEMENT"]
            )
        
        if not self.graph_stitch_relation_priority:
            self.graph_stitch_relation_priority = [
                "resolves_to", "calls", "overrides", "uses", "imports", "inherits", "type_annotates"
            ]
        self.granularity_mixing_profiles = self._normalize_granularity_mixing_profiles(
            self.granularity_mixing_profiles
        )

    @staticmethod
    def _default_granularity_mixing_profiles() -> dict:
        """Deterministic fallback granularity mix profile."""
        return {
            "EXPLAIN": {
                "fine": {"min": 3, "max": 8},
                "medium": {"min": 2, "max": 6},
                "coarse": {"min": 1, "max": 4},
            },
            "IMPLEMENT": {
                "fine": {"min": 8, "max": 15},
                "medium": {"min": 1, "max": 4},
                "coarse": {"min": 0, "max": 1},
            },
            "DEBUG": {
                "fine": {"min": 10, "max": 18},
                "medium": {"min": 1, "max": 3},
                "coarse": {"min": 0, "max": 1},
            },
            "SEARCH": {
                "fine": {"min": 2, "max": 5},
                "medium": {"min": 3, "max": 8},
                "coarse": {"min": 2, "max": 5},
            },
            "REFACTOR": {
                "fine": {"min": 6, "max": 12},
                "medium": {"min": 2, "max": 5},
                "coarse": {"min": 1, "max": 2},
            },
            "UNKNOWN": {
                "fine": {"min": 5, "max": 10},
                "medium": {"min": 2, "max": 5},
                "coarse": {"min": 1, "max": 2},
            },
        }

    @staticmethod
    def _default_query_expansion_synonyms() -> dict:
        """Deterministic lexical-only expansion table."""
        return {
            "auth": ["authentication", "authorize", "authorization", "login"],
            "authentication": ["auth", "authorize", "authorization", "login"],
            "login": ["signin", "authentication", "auth"],
            "signin": ["login", "authentication", "auth"],
            "function": ["method", "routine", "handler"],
            "method": ["function", "routine"],
            "module": ["package", "file", "component"],
            "bug": ["issue", "error", "failure"],
            "fix": ["repair", "patch", "resolve"],
            "import": ["dependency", "module"],
            "resolve": ["resolution", "lookup"],
            "cache": ["caching", "memoization"],
        }

    @classmethod
    def _normalize_query_expansion_synonyms(cls, raw_synonyms: dict) -> dict:
        """Validate/normalize deterministic query-expansion synonym map."""
        synonyms = deepcopy(raw_synonyms) if raw_synonyms else cls._default_query_expansion_synonyms()
        if not isinstance(synonyms, dict):
            raise ValueError("retrieval.query_expansion.synonyms must be a mapping")

        normalized: dict[str, tuple[str, ...]] = {}
        for key, values in synonyms.items():
            term = str(key).strip().lower()
            if not term:
                continue
            if not isinstance(values, (list, tuple)):
                raise ValueError(
                    f"retrieval.query_expansion.synonyms.{term} must be a list/tuple"
                )

            dedup: list[str] = []
            seen: set[str] = set()
            for raw_value in values:
                candidate = str(raw_value).strip().lower()
                if not candidate or candidate == term or candidate in seen:
                    continue
                seen.add(candidate)
                dedup.append(candidate)
            if dedup:
                normalized[term] = tuple(dedup)

        return normalized

    @classmethod
    def _normalize_granularity_mixing_profiles(cls, raw_profiles: dict) -> dict:
        """Validate and normalize config-driven granularity mix profiles."""
        profiles = deepcopy(raw_profiles) if raw_profiles else cls._default_granularity_mixing_profiles()
        if not isinstance(profiles, dict):
            raise ValueError("retrieval.granularity_mixing.profiles must be a mapping")

        normalized: dict[str, dict[str, dict[str, int]]] = {}
        required_levels = ("fine", "medium", "coarse")

        for intent_key, level_cfg in profiles.items():
            intent_name = str(intent_key).strip().upper()
            if not intent_name:
                raise ValueError("retrieval.granularity_mixing.profiles has an empty intent key")
            if not isinstance(level_cfg, dict):
                raise ValueError(
                    f"retrieval.granularity_mixing.profiles.{intent_name} must be a mapping"
                )

            normalized_levels: dict[str, dict[str, int]] = {}
            for level in required_levels:
                if level not in level_cfg:
                    raise ValueError(
                        f"retrieval.granularity_mixing.profiles.{intent_name}.{level} is required"
                    )

                bounds = level_cfg[level]
                if isinstance(bounds, dict):
                    min_raw = bounds.get("min")
                    max_raw = bounds.get("max")
                elif isinstance(bounds, (list, tuple)) and len(bounds) == 2:
                    min_raw, max_raw = bounds
                else:
                    raise ValueError(
                        f"retrieval.granularity_mixing.profiles.{intent_name}.{level} "
                        "must be {min,max} or [min,max]"
                    )

                try:
                    minimum = int(min_raw)
                    maximum = int(max_raw)
                except (TypeError, ValueError):
                    raise ValueError(
                        f"retrieval.granularity_mixing.profiles.{intent_name}.{level} "
                        "min/max must be integers"
                    ) from None

                if minimum < 0 or maximum < 0:
                    raise ValueError(
                        f"retrieval.granularity_mixing.profiles.{intent_name}.{level} "
                        "min/max must be >= 0"
                    )
                if minimum > maximum:
                    raise ValueError(
                        f"retrieval.granularity_mixing.profiles.{intent_name}.{level} "
                        "min cannot exceed max"
                    )
                normalized_levels[level] = {"min": minimum, "max": maximum}

            normalized[intent_name] = normalized_levels

        if "EXPLAIN" not in normalized and "EXPLANATORY" in normalized:
            normalized["EXPLAIN"] = deepcopy(normalized["EXPLANATORY"])
        if "IMPLEMENT" not in normalized and "IMPLEMENTATION" in normalized:
            normalized["IMPLEMENT"] = deepcopy(normalized["IMPLEMENTATION"])
        if "UNKNOWN" not in normalized:
            raise ValueError("retrieval.granularity_mixing.profiles must include UNKNOWN profile")

        for required_intent in ("EXPLAIN", "IMPLEMENT", "REFACTOR", "DEBUG", "SEARCH"):
            if required_intent not in normalized:
                normalized[required_intent] = deepcopy(normalized["UNKNOWN"])

        return normalized

