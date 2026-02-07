"""Retrieval pipeline orchestrator.

Extended for Plan B: Retrieval Layer Activation with:
- Legacy index detection (safety-first fallback)
- Diversity-aware MMR (in hybrid merger)
- Intent-driven granularity boosting
- Graph-based structural expansion (GRAPH_STITCH)
"""

import hashlib
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from homllm.common.config import Config
from homllm.common.types import Intent
from homllm.indexer.embedder import QwenEmbedder
from homllm.indexer.storage.duckdb_adapter import DuckDBAdapter
from homllm.indexer.storage.filesystem_adapter import FilesystemAdapter
from homllm.retrieval.bm25 import BM25Retriever
from homllm.retrieval.expander import StructuralExpanderImpl
from homllm.retrieval.hybrid import RRFHybridMerger
from homllm.retrieval.interfaces import (
    RetrievalConfig,
    RetrievalResult,
    StructuralExpander,
)
from homllm.retrieval.precision_recovery import PrecisionRecovery
from homllm.retrieval.preparer import SimpleQueryPreparer
from homllm.retrieval.vector import VectorRetriever

logger = logging.getLogger(__name__)


class RetrievalPipeline:
    """
    Main retrieval pipeline.
    
    Flow: Query → Ingest → Intent Classify → Query Prep → [BM25 ∥ Vector] → Hybrid Merge → Expand → Precision Recovery → Output
    
    Invariants:
    - RET-001: Same query + same index → same candidates
    - RET-002: Never modifies index artifacts
    - RET-003: All thresholds in config, not code
    - RET-004: BM25 and vector search are parallelizable
    - RET-005: Expansion is capped and auditable
    
    Plan B Extensions:
    - Legacy detection: Falls back to pre-Plan-B behavior if index < 2.0
    - Granularity boosting: Intent-driven multiplicative adjustments
    - Graph stitch: BFS expansion on relations table
    """

    def __init__(
        self,
        config: RetrievalConfig,
        bm25_index_path: Path,
        vector_db_path: Path,
        duckdb_path: Optional[Path] = None,
        artifacts_path: Optional[Path] = None,
        embedder: Optional[QwenEmbedder] = None,
        preparer: Optional[object] = None,
        merger: Optional[object] = None,
        expander: Optional[StructuralExpander] = None,
    ):
        """
        Initialize retrieval pipeline.
        
        Args:
            config: Retrieval configuration
            bm25_index_path: Path to Tantivy BM25 index
            vector_db_path: Path to LanceDB vector database
            duckdb_path: Path to DuckDB database (for content loading)
            artifacts_path: Path to index artifacts (for callgraph loading)
            embedder: Embedder for vector search (default: QwenEmbedder)
            preparer: Query preparer (default: SimpleQueryPreparer)
            merger: Hybrid merger (default: RRFHybridMerger)
            expander: Structural expander (default: StructuralExpanderImpl)
        """
        self.config = config
        self.duckdb_path = duckdb_path
        self.embedder = embedder or QwenEmbedder()
        self.preparer = preparer or SimpleQueryPreparer()
        # Pass embedder to merger for MMR
        self.merger = merger or RRFHybridMerger(embedder=self.embedder)
        self.expander = expander or StructuralExpanderImpl(self.embedder, duckdb_path=duckdb_path)
        self.artifacts_path = artifacts_path

        # Initialize retrievers
        self.bm25_retriever = BM25Retriever(bm25_index_path, duckdb_path=duckdb_path)
        self.vector_retriever = VectorRetriever(vector_db_path, self.embedder)
        
        # Initialize precision recovery
        self.precision_recovery = PrecisionRecovery(
            self.bm25_retriever, self.vector_retriever
        )
        
        # Plan B: Initialize DuckDB adapter for schema version check
        self._duckdb: Optional[DuckDBAdapter] = None
        if duckdb_path:
            try:
                self._duckdb = DuckDBAdapter(duckdb_path)
                self._duckdb.connect()
            except Exception as e:
                logger.warning(f"Failed to initialize DuckDB for Plan B: {e}")
        
        # Plan B: Initialize graph stitch expander
        self._graph_stitch_expander = None
        if config.plan_b_enabled and config.graph_stitch_enabled and duckdb_path:
            try:
                from homllm.retrieval.graph_stitch import GraphStitchExpander, GraphStitchConfig
                
                graph_config = GraphStitchConfig(
                    enabled=config.graph_stitch_enabled,
                    max_depth=config.graph_stitch_max_depth,
                    max_additions=config.graph_stitch_max_additions,
                    min_confidence=config.graph_stitch_min_confidence,
                    relation_priority=config.graph_stitch_relation_priority,
                    graph_cache_enabled=config.graph_cache_enabled,
                    beam_high=config.graph_stitch_beam_high,
                    beam_low=config.graph_stitch_beam_low,
                )
                self._graph_stitch_expander = GraphStitchExpander(duckdb_path, graph_config)
            except Exception as e:
                logger.warning(f"Failed to initialize graph stitch: {e}")

    def retrieve(
        self, query: str, intent: Intent = Intent.UNKNOWN, top_k: int = 50
    ) -> RetrievalResult:
        """
        Execute retrieval pipeline.
        
        Args:
            query: User query
            intent: Query intent (default: UNKNOWN)
            top_k: Maximum number of candidates to return
        
        Returns:
            RetrievalResult with candidates and metadata
        
        Guarantees:
        - Deterministic for same query + same index
        - Never modifies index artifacts
        - All thresholds from config
        """
        query_id = str(uuid.uuid4())

        try:
            t0 = time.perf_counter()
            # =================================================================
            # Plan B: Step 1 — Legacy Index Detection
            # =================================================================
            is_legacy = self._detect_legacy_index()
            plan_b_active = self.config.plan_b_enabled and not is_legacy
            
            if is_legacy and self.config.plan_b_enabled:
                logger.warning(
                    "Legacy index detected (version < 2.0), Plan B features disabled. "
                    "legacy_retrieval_active=true"
                )
            elif plan_b_active:
                logger.info("Plan B: Retrieval layer activation ENABLED")
            
            # 1. Prepare query
            prep_start = time.perf_counter()
            prepared = self.preparer.prepare(query, intent)
            prep_ms = (time.perf_counter() - prep_start) * 1000

            # 2. Parallel search: BM25 and Vector
            bm25_results = []
            vector_results = []

            # BM25 search
            try:
                bm25_start = time.perf_counter()
                bm25_results = self.bm25_retriever.search(
                    " ".join(prepared.lexical_terms), self.config.bm25_top_k
                )
                bm25_ms = (time.perf_counter() - bm25_start) * 1000
            except Exception as e:
                logger.error(f"BM25 search failed: {e}")
                bm25_ms = None
                # Continue with vector-only results (RET-004)

            # Vector search
            try:
                vector_start = time.perf_counter()
                vector_results = self.vector_retriever.search(
                    prepared.dense_query, self.config.vector_top_k
                )
                vector_ms = (time.perf_counter() - vector_start) * 1000
            except Exception as e:
                logger.error(f"Vector search failed: {e}")
                vector_ms = None
                # Continue with BM25-only results (RET-004)

            # If both failed, return empty result
            if not bm25_results and not vector_results:
                logger.warning("Both BM25 and vector search failed")
                return RetrievalResult(
                    candidates=[],
                    query_id=query_id,
                    metadata={"error": "both_searches_failed"},
                )

            # 3. Hybrid merge
            merge_start = time.perf_counter()
            apply_mmr_in_merge = self.config.post_merge_candidates <= 0
            merged = self.merger.merge(
                bm25_results,
                vector_results,
                self.config,
                apply_mmr=apply_mmr_in_merge,
            )
            merge_ms = (time.perf_counter() - merge_start) * 1000

            # Post-merge cap (applied before MMR/graph/expansion)
            if self.config.post_merge_candidates and len(merged) > self.config.post_merge_candidates:
                merged = merged[: self.config.post_merge_candidates]
            
            # MMR (if not applied in merge)
            if not apply_mmr_in_merge:
                mmr_start = time.perf_counter()
                merged = self.merger.apply_mmr(merged, self.config)
                mmr_ms = (time.perf_counter() - mmr_start) * 1000
            else:
                mmr_ms = 0.0
            
            # =================================================================
            # Plan B: Step 3 — Intent-Driven Granularity Boosting
            # =================================================================
            if plan_b_active and self.config.granularity_boost_enabled:
                gran_start = time.perf_counter()
                merged = self._apply_granularity_boost(merged, intent)
                granularity_ms = (time.perf_counter() - gran_start) * 1000
            else:
                granularity_ms = 0.0

            # 4. Structural expansion
            if self.config.expansion_enabled:
                # Plan B: Step 4 — Graph Stitch first, then legacy expansion
                if plan_b_active and self._graph_stitch_expander:
                    gs_start = time.perf_counter()
                    merged = self._graph_stitch_expander.expand(merged, query)
                    graph_stitch_ms = (time.perf_counter() - gs_start) * 1000
                else:
                    graph_stitch_ms = 0.0
                
                # Legacy expansion (callgraph-based)
                callgraph = self._load_callgraph()
                exp_start = time.perf_counter()
                merged = self.expander.expand(merged, query, callgraph, self.config)
                expansion_ms = (time.perf_counter() - exp_start) * 1000
            else:
                graph_stitch_ms = 0.0
                expansion_ms = 0.0

            # 5. Precision recovery (missing entity detection)
            pr_start = time.perf_counter()
            merged = self.precision_recovery.recover(
                merged, query, self.config, max_additions=3
            )
            precision_ms = (time.perf_counter() - pr_start) * 1000

            # 6. Limit to top_k
            final_candidates = merged[:top_k]
            total_ms = (time.perf_counter() - t0) * 1000

            logger.info(
                "[RETRIEVAL_PROFILE] prep_ms=%.1f bm25_ms=%s vector_ms=%s merge_ms=%.1f mmr_ms=%.1f granularity_ms=%.1f graph_stitch_ms=%.1f expansion_ms=%.1f precision_ms=%.1f total_ms=%.1f",
                prep_ms,
                f"{bm25_ms:.1f}" if bm25_ms is not None else "NA",
                f"{vector_ms:.1f}" if vector_ms is not None else "NA",
                merge_ms,
                mmr_ms,
                granularity_ms,
                graph_stitch_ms,
                expansion_ms,
                precision_ms,
                total_ms,
            )

            return RetrievalResult(
                candidates=final_candidates,
                query_id=query_id,
                metadata={
                    "bm25_count": len(bm25_results),
                    "vector_count": len(vector_results),
                    "merged_count": len(merged),
                    "final_count": len(final_candidates),
                    "plan_b_active": plan_b_active,
                    "is_legacy_index": is_legacy,
                    "prep_ms": round(prep_ms, 2),
                    "bm25_ms": round(bm25_ms, 2) if bm25_ms is not None else None,
                    "vector_ms": round(vector_ms, 2) if vector_ms is not None else None,
                    "merge_ms": round(merge_ms, 2),
                    "mmr_ms": round(mmr_ms, 2),
                    "granularity_ms": round(granularity_ms, 2),
                    "graph_stitch_ms": round(graph_stitch_ms, 2),
                    "expansion_ms": round(expansion_ms, 2),
                    "precision_ms": round(precision_ms, 2),
                    "total_ms": round(total_ms, 2),
                    "mmr_candidates": getattr(self.merger, "last_metrics", {}).get("mmr_candidates"),
                    "mmr_emb_ms": getattr(self.merger, "last_metrics", {}).get("mmr_emb_ms"),
                    "mmr_ms": getattr(self.merger, "last_metrics", {}).get("mmr_ms"),
                    "mmr_error": getattr(self.merger, "last_metrics", {}).get("mmr_error"),
                },
            )

        except Exception as e:
            logger.error(f"Retrieval pipeline failed: {e}")
            return RetrievalResult(
                candidates=[],
                query_id=query_id,
                metadata={"error": str(e)},
            )
    
    def _detect_legacy_index(self) -> bool:
        """
        Detect if running on a legacy index (pre-Plan-A).
        
        Plan B Step 1: Safety check before enabling new features.
        """
        if not self._duckdb:
            return True  # Assume legacy if no DuckDB
        
        try:
            version = self._duckdb.get_schema_version()
            is_legacy = version < "2.0"
            
            if is_legacy:
                logger.debug(f"Legacy index detected: version={version}")
            
            return is_legacy
        except Exception as e:
            logger.debug(f"Schema version check failed: {e}")
            return True  # Assume legacy on error
    
    def _apply_granularity_boost(
        self,
        candidates: list,
        intent: Intent,
    ) -> list:
        """
        Apply intent-driven granularity boosting.
        
        Plan B Step 3: Multiplicative score adjustment based on chunk granularity.
        """
        try:
            from homllm.retrieval.granularity_booster import (
                apply_granularity_boost,
                build_granularity_lookup,
            )
            
            # Build granularity lookup from DuckDB
            granularity_lookup = {}
            if self._duckdb:
                doc_ids = [c.doc_id for c in candidates]
                granularity_lookup = build_granularity_lookup(self._duckdb, doc_ids)
            
            if not granularity_lookup:
                logger.debug("Granularity boost: No lookup data, skipping")
                return candidates
            
            return apply_granularity_boost(
                candidates,
                intent,
                boost_table=self.config.granularity_boost_table,
                granularity_lookup=granularity_lookup,
            )
        except Exception as e:
            logger.warning(f"Granularity boost failed: {e}")
            return candidates

    def _load_callgraph(self) -> dict:
        """Load callgraph from artifacts."""
        if not self.artifacts_path:
            logger.warning("Artifacts path not provided, returning empty callgraph")
            return {}

        try:
            fs_adapter = FilesystemAdapter(self.artifacts_path)
            if fs_adapter.exists("callgraph.json"):
                callgraph_data = fs_adapter.read_json("callgraph.json")
                # Convert to dict format expected by expander: {caller_id: [callee_id, ...]}
                callgraph = {}
                for edge in callgraph_data.get("edges", []):
                    caller_id = edge.get("caller_id")
                    callee_id = edge.get("callee_id")
                    if caller_id and callee_id:
                        if caller_id not in callgraph:
                            callgraph[caller_id] = []
                        callgraph[caller_id].append(callee_id)
                return callgraph
            else:
                logger.warning("callgraph.json not found in artifacts")
                return {}
        except Exception as e:
            logger.warning(f"Failed to load callgraph: {e}")
            return {}

