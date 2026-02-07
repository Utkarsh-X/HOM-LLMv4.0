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


@dataclass
class IndexerConfig:
    """Indexer layer configuration."""

    languages: list[str]
    ignore_patterns: list[str]
    chunk_max_lines: int
    storage: StorageConfig
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_dimension: int = 1024
    embedding_max_tokens: int = 8192
    # Entity-centric indexing (Plan A)
    entity_centric_indexing_enabled: bool = True
    type_alias_extraction_enabled: bool = False  # Disabled by default
    entity_confidence: EntityConfidenceConfig = None
    hierarchical_chunking: HierarchicalChunkingConfig = None

    def __post_init__(self):
        if self.entity_confidence is None:
            self.entity_confidence = EntityConfidenceConfig()
        if self.hierarchical_chunking is None:
            self.hierarchical_chunking = HierarchicalChunkingConfig()


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
        )
        
        return IndexerConfig(
            languages=idx_cfg["languages"],
            ignore_patterns=idx_cfg["ignore_patterns"],
            chunk_max_lines=idx_cfg["chunk_max_lines"],
            storage=storage_cfg,
            embedding_model=idx_cfg.get("embedding_model", "Qwen/Qwen3-Embedding-0.6B"),
            embedding_dimension=idx_cfg.get("embedding_dimension", 1024),
            embedding_max_tokens=idx_cfg.get("embedding_max_tokens", 8192),
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
        
        # Plan B config sections
        diversity_mmr_cfg = ret_cfg.get("diversity_mmr", {})
        granularity_boost_cfg = ret_cfg.get("granularity_boost", {})
        graph_stitch_cfg = ret_cfg.get("graph_stitch", {})

        return RetrievalConfig(
            # Core retrieval settings
            bm25_top_k=ret_cfg.get("bm25", {}).get("top_k", 50),
            vector_top_k=ret_cfg.get("vector", {}).get("top_k", 50),
            hybrid_method=hybrid_cfg.get("method", "rrf"),
            rrf_k=hybrid_cfg.get("rrf_k", 10),
            bm25_weight=hybrid_cfg.get("bm25_weight", 0.5),
            vector_weight=hybrid_cfg.get("vector_weight", 0.5),
            expansion_enabled=expansion_cfg.get("enabled", True),
            expansion_max_additions=expansion_cfg.get("max_additions", 4),
            expansion_min_similarity=expansion_cfg.get("min_similarity", 0.25),
            
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
                ["calls", "overrides", "imports", "uses", "inherits", "type_annotates"]
            ),
            graph_cache_enabled=graph_stitch_cfg.get("graph_cache_enabled", True),
            graph_stitch_beam_high=graph_stitch_cfg.get("graph_stitch_beam_high", 8),
            graph_stitch_beam_low=graph_stitch_cfg.get("graph_stitch_beam_low", 3),
            post_merge_candidates=ret_cfg.get("post_merge_candidates", 0),
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

    def get_ranking_config(self) -> "RankConfig":
        """Extract RankConfig from root config."""
        from homllm.ranking.interfaces import RankConfig

        rank_cfg = self.ranking
        reranker_cfg = rank_cfg.get("reranker", {})
        weights_cfg = rank_cfg.get("weights", {})

        struct_weights = weights_cfg.get("struct", {})
        return RankConfig(
            reranker_enabled=reranker_cfg.get("enabled", True),
            reranker_model=reranker_cfg.get("model", "Qwen/Qwen3-Reranker-0.6B"),
            reranker_top_m=reranker_cfg.get("top_m", 40),
            w_base=weights_cfg.get("w_base", 0.4),
            w_rerank=weights_cfg.get("w_rerank", 0.55),
            w_struct=weights_cfg.get("w_struct", 0.05),
            w_bm25=weights_cfg.get("w_bm25", 0.4),
            w_dense=weights_cfg.get("w_dense", 0.4),
            w_name=weights_cfg.get("w_name", 0.2),
            struct_entrypoint_bonus=struct_weights.get("entrypoint_bonus", 0.1),
            struct_decorator_bonus=struct_weights.get("decorator_bonus", 0.05),
            struct_callgraph_bonus=struct_weights.get("callgraph_bonus", 0.05),
            struct_bonus_cap=struct_weights.get("bonus_cap", 0.2),
        )

    def get_context_config(self) -> "ContextConfig":
        """Extract ContextConfig from root config."""
        from homllm.context.interfaces import ContextConfig

        ctx_cfg = self.context

        scoring_weights = ctx_cfg.get("scoring_weights", {})
        
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

