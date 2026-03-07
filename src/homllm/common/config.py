"""Configuration management."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


@dataclass
class StorageConfig:
    """Storage adapter configuration."""

    duckdb_path: Path
    tantivy_path: Path
    lancedb_path: Path
    artifacts_path: Path


# =============================================================================
# Entity-Centric Indexing Config (Plan A)
# =============================================================================


@dataclass
class EntityConfidenceConfig:
    """Configuration for deterministic entity confidence scoring."""

    public_name_bonus: float = 0.3
    docstring_bonus: float = 0.4
    exported_bonus: float = 0.2
    type_annotated_bonus: float = 0.1
    cap_at: float = 1.0


@dataclass
class HierarchicalChunkingConfig:
    """Configuration for 3-level hierarchical chunking."""

    enabled: bool = True
    fine_enabled: bool = True       # Symbol-level
    medium_enabled: bool = True     # File sections
    coarse_enabled: bool = True     # File-level
    chunk_max_lines: int = 100

    def __post_init__(self):
        self.chunk_max_lines = max(1, int(self.chunk_max_lines))


@dataclass
class IndexerConfig:
    """Indexer layer configuration."""

    languages: list[str]
    ignore_patterns: list[str]
    chunk_max_lines: int
    storage: StorageConfig
    vector_indexing_enabled: bool = True
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_dimension: int = 1024
    embedding_max_tokens: int = 8192
    embedding_device: str = "auto"
    # Entity-centric indexing (Plan A)
    entity_centric_indexing_enabled: bool = True
    type_alias_extraction_enabled: bool = False  # Disabled by default
    entity_confidence: EntityConfidenceConfig = None
    hierarchical_chunking: HierarchicalChunkingConfig = None

    def __post_init__(self):
        self.chunk_max_lines = max(1, int(self.chunk_max_lines))
        if self.entity_confidence is None:
            self.entity_confidence = EntityConfidenceConfig()
        if self.hierarchical_chunking is None:
            self.hierarchical_chunking = HierarchicalChunkingConfig()
        else:
            self.hierarchical_chunking.chunk_max_lines = self.chunk_max_lines


@dataclass
class IntelligenceConfig:
    """Intelligence layer configuration."""

    enabled: bool = True
    level1_enabled: bool = True
    level2_enabled: bool = True
    level3_enabled: bool = True


class Config(BaseModel):
    """Root configuration."""

    indexer: dict
    retrieval: dict
    ranking: dict
    context: dict
    intelligence: dict = {}
    generation: dict
    evaluation: dict

    @classmethod
    def from_file(cls, path: Path) -> "Config":
        """Load configuration from YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def get_indexer_config(self) -> IndexerConfig:
        """Extract IndexerConfig from root config."""
        idx_cfg = self.indexer
        storage_cfg = StorageConfig(
            duckdb_path=Path(idx_cfg["storage"]["duckdb_path"]),
            tantivy_path=Path(idx_cfg["storage"]["tantivy_path"]),
            lancedb_path=Path(idx_cfg["storage"]["lancedb_path"]),
            artifacts_path=Path(idx_cfg["storage"]["artifacts_path"]),
        )
        
        # Parse entity confidence config
        confidence_cfg = idx_cfg.get("entity_confidence", {})
        entity_confidence = EntityConfidenceConfig(
            public_name_bonus=confidence_cfg.get("public_name_bonus", 0.3),
            docstring_bonus=confidence_cfg.get("docstring_bonus", 0.4),
            exported_bonus=confidence_cfg.get("exported_bonus", 0.2),
            type_annotated_bonus=confidence_cfg.get("type_annotated_bonus", 0.1),
            cap_at=confidence_cfg.get("cap_at", 1.0),
        )
        
        # Parse hierarchical chunking config
        chunking_cfg = idx_cfg.get("hierarchical_chunking", {})
        hierarchical_chunking = HierarchicalChunkingConfig(
            enabled=chunking_cfg.get("enabled", True),
            fine_enabled=chunking_cfg.get("fine_enabled", True),
            medium_enabled=chunking_cfg.get("medium_enabled", True),
            coarse_enabled=chunking_cfg.get("coarse_enabled", True),
            chunk_max_lines=chunking_cfg.get("chunk_max_lines", idx_cfg.get("chunk_max_lines", 100)),
        )
        
        return IndexerConfig(
            languages=idx_cfg["languages"],
            ignore_patterns=idx_cfg["ignore_patterns"],
            chunk_max_lines=idx_cfg["chunk_max_lines"],
            storage=storage_cfg,
            vector_indexing_enabled=idx_cfg.get("vector_indexing_enabled", True),
            embedding_model=idx_cfg.get("embedding_model", "Qwen/Qwen3-Embedding-0.6B"),
            embedding_dimension=idx_cfg.get("embedding_dimension", 1024),
            embedding_max_tokens=idx_cfg.get("embedding_max_tokens", 8192),
            embedding_device=idx_cfg.get("embedding_device", "auto"),
            entity_centric_indexing_enabled=idx_cfg.get("entity_centric_indexing_enabled", True),
            type_alias_extraction_enabled=idx_cfg.get("type_alias_extraction_enabled", False),
            entity_confidence=entity_confidence,
            hierarchical_chunking=hierarchical_chunking,
        )

    def get_retrieval_config(self) -> "RetrievalConfig":
        """Extract RetrievalConfig from root config."""
        from homllm.retrieval.interfaces import RetrievalConfig

        ret_cfg = self.retrieval
        hybrid_cfg = ret_cfg.get("hybrid", {})
        expansion_cfg = ret_cfg.get("expansion", {})
        static_ceiling_cfg = ret_cfg.get("static_ceiling_experiment", {})
        precision_recovery_cfg = ret_cfg.get("precision_recovery", {})
        
        # Plan B config sections
        diversity_mmr_cfg = ret_cfg.get("diversity_mmr", {})
        granularity_boost_cfg = ret_cfg.get("granularity_boost", {})
        graph_stitch_cfg = ret_cfg.get("graph_stitch", {})
        budget_cfg = ret_cfg.get("budget", {})
        granularity_mix_cfg = ret_cfg.get("granularity_mixing", {})
        dedup_cfg = ret_cfg.get("hierarchical_dedup", {})
        query_expansion_cfg = ret_cfg.get("query_expansion", {})

        # RET-IMP-08: Single budget authority.
        # Retrieval must consume context budget values from one source only.
        dual_authority_keys = [k for k in ("context_budget", "reserve") if k in budget_cfg]
        if dual_authority_keys:
            raise ValueError(
                "Dual budget authority detected: retrieval.budget."
                + ",".join(sorted(dual_authority_keys))
                + " is not allowed. Use context.max_tokens and "
                "context.generation_reserve_tokens as the single authority."
            )

        ctx_cfg = self.context if isinstance(self.context, dict) else {}
        context_max_tokens = int(ctx_cfg.get("max_tokens", 4000))
        context_default_reserve = max(int(context_max_tokens * 0.2), 400)
        context_generation_reserve = int(
            ctx_cfg.get("generation_reserve_tokens", context_default_reserve)
        )

        return RetrievalConfig(
            # Core retrieval settings
            bm25_top_k=ret_cfg.get("bm25", {}).get("top_k", 50),
            vector_top_k=ret_cfg.get("vector", {}).get("top_k", 50),
            vector_calibration_mode=ret_cfg.get("vector", {}).get("calibration_mode", "legacy"),
            hybrid_method=hybrid_cfg.get("method", "rrf"),
            rrf_k=hybrid_cfg.get("rrf_k", 10),
            bm25_weight=hybrid_cfg.get("bm25_weight", 0.5),
            vector_weight=hybrid_cfg.get("vector_weight", 0.5),
            parallel_search_enabled=ret_cfg.get("parallel_search", {}).get("enabled", True),
            expansion_enabled=expansion_cfg.get("enabled", True),
            expansion_max_additions=expansion_cfg.get("max_additions", 4),
            expansion_min_similarity=expansion_cfg.get("min_similarity", 0.25),
            static_ceiling_experiment_enabled=static_ceiling_cfg.get("enabled", False),
            static_ceiling_branch_multiplier=static_ceiling_cfg.get("branch_multiplier", 1),
            static_ceiling_post_merge_multiplier=static_ceiling_cfg.get("post_merge_multiplier", 1),
            static_ceiling_output_multiplier=static_ceiling_cfg.get("output_multiplier", 1),
            precision_recovery_enabled=precision_recovery_cfg.get("enabled", True),
            precision_recovery_max_additions=precision_recovery_cfg.get("max_additions", 3),
            precision_recovery_max_ratio=precision_recovery_cfg.get("max_ratio", 0.2),
            precision_recovery_scan_candidates=precision_recovery_cfg.get("scan_candidates", 8),
            precision_recovery_identifier_limit=precision_recovery_cfg.get("identifier_limit", 16),
            precision_recovery_bm25_top_k=precision_recovery_cfg.get("bm25_top_k", 5),
            precision_recovery_vector_top_k=precision_recovery_cfg.get("vector_top_k", 3),
            precision_recovery_min_confidence=precision_recovery_cfg.get("min_confidence", 0.8),
            query_expansion_enabled=query_expansion_cfg.get("enabled", True),
            query_expansion_max_terms=query_expansion_cfg.get("max_terms", 6),
            query_expansion_min_token_length=query_expansion_cfg.get("min_token_length", 3),
            query_expansion_synonyms=query_expansion_cfg.get("synonyms", {}),
            
            # Plan B: Retrieval Layer Activation
            plan_b_enabled=ret_cfg.get("plan_b_enabled", True),
            
            # Diversity-aware MMR
            diversity_mmr_enabled=diversity_mmr_cfg.get("enabled", True),
            mmr_lambda=diversity_mmr_cfg.get("lambda", 0.6),
            mmr_similarity_threshold=diversity_mmr_cfg.get("similarity_threshold", 0.85),
            
            # Granularity boosting
            granularity_boost_enabled=granularity_boost_cfg.get("enabled", True),
            granularity_boost_table=self._parse_granularity_boost_table(granularity_boost_cfg),
            
            # Graph stitch
            graph_stitch_enabled=graph_stitch_cfg.get("enabled", True),
            graph_stitch_max_depth=graph_stitch_cfg.get("max_depth", 2),
            graph_stitch_max_additions=graph_stitch_cfg.get("max_additions", 8),
            graph_stitch_min_confidence=graph_stitch_cfg.get("min_confidence", 0.5),
            graph_stitch_relation_priority=graph_stitch_cfg.get(
                "relation_priority",
                ["resolves_to", "calls", "overrides", "uses", "imports", "inherits", "type_annotates"]
            ),
            graph_cache_enabled=graph_stitch_cfg.get("graph_cache_enabled", True),
            graph_stitch_beam_high=graph_stitch_cfg.get("graph_stitch_beam_high", 8),
            graph_stitch_beam_low=graph_stitch_cfg.get("graph_stitch_beam_low", 3),
            post_merge_candidates=ret_cfg.get("post_merge_candidates", 0),
            context_budget=context_max_tokens,
            budget_reserve=context_generation_reserve,
            budget_aware_selection=budget_cfg.get("enabled", True),
            granularity_mixing_enabled=granularity_mix_cfg.get("enabled", True),
            granularity_mixing_profiles=self._parse_granularity_mixing_profiles(granularity_mix_cfg),
            hierarchical_dedup_enabled=dedup_cfg.get("enabled", True),
            # Tier 3B: Adaptive retrieval geometry
            adaptive_seed_enabled=ret_cfg.get("adaptive_seed", {}).get("enabled", False),
            adaptive_seed_min_k=ret_cfg.get("adaptive_seed", {}).get("min_k", 20),
            adaptive_seed_max_k=ret_cfg.get("adaptive_seed", {}).get("max_k", 150),
            adaptive_seed_drop_threshold=ret_cfg.get("adaptive_seed", {}).get("drop_threshold", 0.30),
        )
    
    def _parse_granularity_boost_table(self, cfg: dict) -> dict:
        """Parse granularity boost table from config."""
        # Extract intent-specific boost tables
        # Keys must match Intent enum: EXPLAIN, IMPLEMENT, REFACTOR, DEBUG, SEARCH, UNKNOWN
        table = {}
        for intent in ["EXPLAIN", "IMPLEMENT", "REFACTOR", "DEBUG", "SEARCH", "UNKNOWN"]:
            if intent in cfg:
                table[intent] = cfg[intent]
        return table  # Empty dict triggers defaults in RetrievalConfig.__post_init__

    def _parse_granularity_mixing_profiles(self, cfg: dict) -> dict:
        """Parse granularity mixing profiles from config."""
        if not isinstance(cfg, dict):
            return {}
        profiles = cfg.get("profiles")
        if isinstance(profiles, dict):
            return profiles

        # Backward-compatible shape: intent keys directly under granularity_mixing.
        table = {}
        for intent in [
            "EXPLAIN",
            "IMPLEMENT",
            "REFACTOR",
            "DEBUG",
            "SEARCH",
            "UNKNOWN",
            "EXPLANATORY",
            "IMPLEMENTATION",
        ]:
            if intent in cfg:
                table[intent] = cfg[intent]
        return table

    def get_ranking_config(self) -> "RankConfig":
        """Extract RankConfig from root config."""
        from homllm.ranking.interfaces import RankConfig

        rank_cfg = self.ranking
        reranker_cfg = rank_cfg.get("reranker", {})
        weights_cfg = rank_cfg.get("weights", {})
        gating_cfg = reranker_cfg.get("gating", {})
        graph_cfg = rank_cfg.get("graph_proximity", {})
        dedup_cfg = rank_cfg.get("dedup", {})
        phase2_cfg = rank_cfg.get("phase2", {})
        two_pass_cfg = rank_cfg.get("two_pass", {})
        mmr_cfg = rank_cfg.get("mmr_selection", {})
        set_opt_cfg = rank_cfg.get("set_optimization", {})
        geometry_cfg = rank_cfg.get("geometry", {})

        struct_weights = weights_cfg.get("struct", {})
        return RankConfig(
            reranker_enabled=reranker_cfg.get("enabled", True),
            reranker_model=reranker_cfg.get("model", "Qwen/Qwen3-Reranker-0.6B"),
            reranker_device=reranker_cfg.get("device", "auto"),
            reranker_top_m=reranker_cfg.get("top_m", 35),
            reranker_bm25_rescue_top_k=reranker_cfg.get("bm25_rescue_top_k", 15),
            # Canonical fusion weights (D1). geometry.rerank_alpha/struct_gamma are deprecated aliases.
            w_base=weights_cfg.get("w_base", 1.0),
            w_rerank=weights_cfg.get("w_rerank", geometry_cfg.get("rerank_alpha", 0.32)),
            w_struct=weights_cfg.get("w_struct", geometry_cfg.get("struct_gamma", 0.05)),
            w_bm25=weights_cfg.get("w_bm25", 0.4),
            w_dense=weights_cfg.get("w_dense", 0.4),
            w_name=weights_cfg.get("w_name", 0.2),
            rerank_alpha=weights_cfg.get("w_rerank", geometry_cfg.get("rerank_alpha", 0.32)),  # alias
            struct_gamma=weights_cfg.get("w_struct", geometry_cfg.get("struct_gamma", 0.05)),  # alias
            struct_entrypoint_bonus=struct_weights.get("entrypoint_bonus", 0.1),
            struct_decorator_bonus=struct_weights.get("decorator_bonus", 0.05),
            struct_callgraph_bonus=struct_weights.get("callgraph_bonus", 0.05),
            struct_bonus_cap=struct_weights.get("bonus_cap", 0.2),
            graph_max_depth=graph_cfg.get("max_depth", 4),
            graph_anchor_k=graph_cfg.get("anchor_k", 5),
            dedup_file_entropy_threshold=dedup_cfg.get(
                "file_entropy_threshold", 0.6
            ),
            reranker_gating_enabled=gating_cfg.get("enabled", True),
            reranker_margin_threshold=gating_cfg.get("threshold_margin", 0.2),
            reranker_entropy_threshold=gating_cfg.get("threshold_entropy", 0.7),
            reranker_disagreement_threshold=gating_cfg.get(
                "threshold_disagreement", 0.5
            ),
            reranker_gating_top_k=gating_cfg.get("top_k", 50),
            reranker_gating_min_candidates=gating_cfg.get(
                "min_candidates", 3
            ),
            phase2_enabled=phase2_cfg.get("enabled", False),
            adaptive_weights_enabled=phase2_cfg.get("adaptive_weights_enabled", False),
            two_pass_enabled=two_pass_cfg.get("enabled", False),
            two_pass_seed_k=two_pass_cfg.get("seed_k", 20),
            two_pass_max_depth=two_pass_cfg.get("max_depth", 3),
            two_pass_decay=two_pass_cfg.get("decay", 0.8),
            mmr_enabled=mmr_cfg.get("enabled", False),
            mmr_top_n=mmr_cfg.get("top_n", 30),
            mmr_lambda=mmr_cfg.get("lambda", 0.7),
            set_opt_enabled=set_opt_cfg.get("enabled", False),
            set_opt_token_budget=set_opt_cfg.get("token_budget", 3200),
            set_opt_w_relevance=set_opt_cfg.get("w_relevance", 1.0),
            set_opt_w_structural=set_opt_cfg.get("w_structural", 0.6),
            set_opt_w_coverage=set_opt_cfg.get("w_coverage", 0.8),
            set_opt_w_redundancy=set_opt_cfg.get("w_redundancy", 0.5),
            set_opt_w_dispersion=set_opt_cfg.get("w_dispersion", 0.4),

            set_opt_max_rounds=set_opt_cfg.get("max_rounds", 100),
            concentration_top_k=rank_cfg.get("concentration_top_k", 10),
        )

    def get_context_config(self) -> "ContextConfig":
        """Extract ContextConfig from root config."""
        from homllm.context.interfaces import ContextConfig

        ctx_cfg = self.context

        scoring_weights = ctx_cfg.get("scoring_weights", {})
        submodular_cfg = ctx_cfg.get("submodular", {})
        
        # Compute safe default for generation reserve: 20% of max_tokens, minimum 400
        max_tokens = ctx_cfg.get("max_tokens", 4000)
        default_reserve = max(int(max_tokens * 0.2), 400)
        
        return ContextConfig(
            max_tokens=max_tokens,
            budget_mode=ctx_cfg.get("budget_mode", "adaptive"),
            summarization_enabled=ctx_cfg.get("summarization_enabled", False),
            ordering=ctx_cfg.get("ordering", "structural_first"),
            structural_priority_multiplier=ctx_cfg.get(
                "structural_priority_multiplier", 1.5
            ),
            generation_reserve_tokens=ctx_cfg.get(
                "generation_reserve_tokens", default_reserve
            ),
            w_semantic=scoring_weights.get("w_semantic", 0.4),
            w_name=scoring_weights.get("w_name", 0.2),
            w_structural=scoring_weights.get("w_structural", 0.2),
            w_novelty=scoring_weights.get("w_novelty", 0.1),
            w_coherence=scoring_weights.get("w_coherence", 0.1),
            structural_priority_entrypoint_bonus=ctx_cfg.get(
                "structural_priority_entrypoint_bonus", 0.5
            ),
            structural_priority_decorator_bonus=ctx_cfg.get(
                "structural_priority_decorator_bonus", 0.3
            ),
            structural_priority_callgraph_bonus=ctx_cfg.get(
                "structural_priority_callgraph_bonus", 0.2
            ),
            structural_priority_cap=ctx_cfg.get("structural_priority_cap", 1.0),
            coherence_same_file_bonus=ctx_cfg.get("coherence_same_file_bonus", 0.8),
            coherence_different_file_bonus=ctx_cfg.get(
                "coherence_different_file_bonus", 0.5
            ),
            ranking_surface_lock_enabled=ctx_cfg.get(
                "ranking_surface_lock_enabled", True
            ),
            # Tier 2: Coherence refinement
            coherence_enabled=ctx_cfg.get("coherence_enabled", True),
            coherence_max_contribution=ctx_cfg.get("coherence_max_contribution", 0.15),
            coherence_protect_top_n=ctx_cfg.get("coherence_protect_top_n", 3),
            coherence_proximity_lines=ctx_cfg.get("coherence_proximity_lines", 50),
            coherence_synergy_threshold=ctx_cfg.get("coherence_synergy_threshold", 0.3),
            coherence_dispersion_threshold=ctx_cfg.get("coherence_dispersion_threshold", 0.9),
            coherence_callgraph_bonus=ctx_cfg.get("coherence_callgraph_bonus", 0.1),
            # Tier 3B: Submodular packer
            submodular_packer_enabled=ctx_cfg.get("submodular_packer_enabled", False),
            submodular_w_rrf=submodular_cfg.get("w_rrf", 0.40),
            submodular_w_novelty=submodular_cfg.get("w_novelty", 0.20),
            submodular_w_graph=submodular_cfg.get("w_graph", 0.20),
            submodular_w_concept=submodular_cfg.get("w_concept", 0.20),
            submodular_min_density_epsilon=submodular_cfg.get(
                "min_density_epsilon", 0.001
            ),
            submodular_novelty_scaling=submodular_cfg.get(
                "novelty_scaling", "none"
            ),
            # Tier 3B: Relevance gate
            relevance_gate_enabled=ctx_cfg.get("relevance_gate_enabled", False),
            relevance_gate_threshold=ctx_cfg.get("relevance_gate_threshold", 0.25),
            # Tier 3C: Precision filter
            precision_filter_enabled=ctx_cfg.get("precision_filter_enabled", False),
            precision_filter_query_identifier_min=ctx_cfg.get(
                "precision_filter_query_identifier_min", 1
            ),
            precision_filter_low_score_threshold=ctx_cfg.get(
                "precision_filter_low_score_threshold", 0.25
            ),
            precision_filter_min_kept_blocks=ctx_cfg.get(
                "precision_filter_min_kept_blocks", 10
            ),
            # Tier 3C: Sparse-context backfill
            sparse_backfill_enabled=ctx_cfg.get("sparse_backfill_enabled", False),
            sparse_backfill_min_utilization=ctx_cfg.get(
                "sparse_backfill_min_utilization", 0.45
            ),
            sparse_backfill_min_blocks=ctx_cfg.get("sparse_backfill_min_blocks", 18),
            sparse_backfill_max_additional_blocks=ctx_cfg.get(
                "sparse_backfill_max_additional_blocks", 10
            ),
            # Claim-gain epsilon swap
            claim_gain_swap_enabled=ctx_cfg.get("claim_gain_swap_enabled", False),
            claim_gain_swap_score_epsilon=ctx_cfg.get(
                "claim_gain_swap_score_epsilon", 0.02
            ),
            claim_gain_swap_max_swaps=ctx_cfg.get("claim_gain_swap_max_swaps", 2),
            claim_gain_swap_min_relevance_floor=ctx_cfg.get(
                "claim_gain_swap_min_relevance_floor",
                ctx_cfg.get("relevance_gate_threshold", 0.25),
            ),
            unresolved_evidence_injection_enabled=ctx_cfg.get(
                "unresolved_evidence_injection_enabled", False
            ),
            unresolved_evidence_injection_max_blocks=ctx_cfg.get(
                "unresolved_evidence_injection_max_blocks", 2
            ),
            unresolved_evidence_injection_min_claim_gain=ctx_cfg.get(
                "unresolved_evidence_injection_min_claim_gain", 0.1
            ),
            unresolved_evidence_injection_relevance_floor=ctx_cfg.get(
                "unresolved_evidence_injection_relevance_floor", 0.15
            ),
            unresolved_evidence_injection_max_token_share=ctx_cfg.get(
                "unresolved_evidence_injection_max_token_share", 0.15
            ),
            unresolved_evidence_injection_replace_from_tail=ctx_cfg.get(
                "unresolved_evidence_injection_replace_from_tail", True
            ),
            # Tier 3B: Escape hatch
            escape_hatch_enabled=ctx_cfg.get("escape_hatch_enabled", False),
        )

    def get_generation_config(self) -> "GenerationConfig":
        """Extract GenerationConfig from root config."""
        from homllm.generation.config import GenerationConfig

        gen_cfg = self.generation

        return GenerationConfig(
            default_provider=gen_cfg.get("default_provider", "gemini"),
            default_model=gen_cfg.get("default_model", "gemini-2.5-flash"),
            default_temperature=gen_cfg.get("temperature", 0.0),
            default_max_output_tokens=gen_cfg.get("max_output_tokens", 2000),
            default_template=gen_cfg.get("default_template", "explain"),
        )

    def get_intelligence_config(self) -> IntelligenceConfig:
        """Extract IntelligenceConfig from root config."""
        int_cfg = self.intelligence or {}

        return IntelligenceConfig(
            enabled=int_cfg.get("enabled", True),
            level1_enabled=int_cfg.get("level1_enabled", True),
            level2_enabled=int_cfg.get("level2_enabled", True),
            level3_enabled=int_cfg.get("level3_enabled", True),
        )

