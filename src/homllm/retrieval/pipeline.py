"""Retrieval pipeline orchestrator.

Extended for Plan B: Retrieval Layer Activation with:
- Legacy index detection (safety-first fallback)
- Diversity-aware MMR (in hybrid merger)
- Intent-driven granularity boosting
- Graph-based structural expansion (GRAPH_STITCH)
"""

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from homllm.common.types import Intent
from homllm.indexer.embedder import QwenEmbedder
from homllm.indexer.storage.duckdb_adapter import DuckDBAdapter
from homllm.indexer.storage.filesystem_adapter import FilesystemAdapter
from homllm.retrieval.bm25 import BM25Retriever
from homllm.retrieval.adaptive_gate import hybrid_knee_gate
from homllm.retrieval.budget import select_candidates_with_budget
from homllm.retrieval.deduplication import deduplicate_hierarchical
from homllm.retrieval.expander import StructuralExpanderImpl
from homllm.retrieval.granularity_strategy import apply_granularity_mix
from homllm.retrieval.hybrid import RRFHybridMerger
from homllm.retrieval.intent_adapter import infer_retrieval_intent
from homllm.retrieval.interfaces import (
    RetrievalConfig,
    RetrievalResult,
    StructuralExpander,
)
from homllm.retrieval.precision_recovery import PrecisionRecovery
from homllm.retrieval.preparer import SimpleQueryPreparer
from homllm.retrieval.vector import VectorRetriever

logger = logging.getLogger(__name__)


def _candidate_order_key(candidate) -> tuple[float, str, str, str]:
    """Deterministic retrieval ordering key."""
    return (
        -float(candidate.hybrid_score),
        str(candidate.doc_id),
        str(candidate.file or ""),
        str(candidate.symbol_id or ""),
    )


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
        self._bm25_index_path = bm25_index_path
        self._vector_db_path = vector_db_path
        self.duckdb_path = duckdb_path
        self.embedder = embedder or QwenEmbedder()
        self.preparer = preparer or SimpleQueryPreparer(config=config)
        # Pass embedder to merger for MMR
        self.merger = merger or RRFHybridMerger(embedder=self.embedder)
        self.expander = expander or StructuralExpanderImpl(self.embedder, duckdb_path=duckdb_path)
        self.artifacts_path = artifacts_path

        # Cache callgraph at init — it's static per index, no need to reload per query
        _cg_start = time.perf_counter()
        self._callgraph_cache: dict = self._load_callgraph()
        _cg_ms = (time.perf_counter() - _cg_start) * 1000
        logger.info("[RETRIEVAL] callgraph cached at init: %d entries, %.1fms",
                    len(self._callgraph_cache), _cg_ms)

        # Initialize retrievers
        self.bm25_retriever = BM25Retriever(bm25_index_path, duckdb_path=duckdb_path)
        self.vector_retriever = VectorRetriever(
            vector_db_path,
            self.embedder,
            duckdb_path=duckdb_path,
            calibration_mode=config.vector_calibration_mode,
        )
        
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
        if not config.plan_b_enabled:
            self._graph_stitch_status = "disabled_plan_b_off"
            self._graph_stitch_status_detail: dict[str, object] = {"reason": "plan_b_disabled"}
        elif not config.graph_stitch_enabled:
            self._graph_stitch_status = "disabled_config_off"
            self._graph_stitch_status_detail = {"reason": "graph_stitch_disabled_in_config"}
        elif not duckdb_path:
            self._graph_stitch_status = "disabled_no_duckdb"
            self._graph_stitch_status_detail = {"reason": "duckdb_path_missing"}
        else:
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
                self._graph_stitch_status = self._graph_stitch_expander.status()
                self._graph_stitch_status_detail = self._graph_stitch_expander.status_detail()
                logger.info(
                    "[GRAPH_STITCH] status=%s detail=%s",
                    self._graph_stitch_status,
                    self._graph_stitch_status_detail,
                )
            except Exception as e:
                logger.warning(f"Failed to initialize graph stitch: {e}")
                self._graph_stitch_status = "disabled_init_error"
                self._graph_stitch_status_detail = {"error": str(e)}

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
            resolved_intent = intent
            intent_source = "caller"
            intent_rule = "provided"
            if resolved_intent == Intent.UNKNOWN:
                inferred_intent = infer_retrieval_intent(query)
                resolved_intent = inferred_intent.intent
                intent_source = inferred_intent.source
                intent_rule = inferred_intent.matched_rule
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
            prepared = self.preparer.prepare(query, resolved_intent)
            prep_ms = (time.perf_counter() - prep_start) * 1000
            if prepared.lexical_expansion_terms:
                logger.info(
                    "[QUERY_EXPANSION] query_id=%s added_terms=%s cap=%s",
                    query_id,
                    ",".join(prepared.lexical_expansion_terms),
                    self.config.query_expansion_max_terms,
                )

            # A4: Adaptive k by query complexity (synthesis/medium/standard)
            requested_k = getattr(prepared, "required_k", top_k)
            requested_k = max(top_k, requested_k)
            if requested_k > 50:
                logger.info(
                    "[RETRIEVAL] adaptive_k=%d (query complexity) candidates_requested=%d",
                    requested_k,
                    requested_k,
                )

            (
                effective_bm25_top_k,
                effective_vector_top_k,
                effective_post_merge_candidates,
                effective_output_top_k,
                static_ceiling_mode,
            ) = self._resolve_static_ceiling_limits(top_k, requested_branch_k=requested_k)

            # 2. BM25 + Vector search (parallel when enabled)
            bm25_results = []
            vector_results = []
            search_mode = "sequential"
            lexical_query = " ".join(prepared.lexical_terms)

            if self.config.parallel_search_enabled:
                bm25_runner, vector_runner, search_mode = self._resolve_parallel_search_runners()
                with ThreadPoolExecutor(max_workers=2) as executor:
                    bm25_future = executor.submit(
                        self._run_bm25_search,
                        bm25_runner,
                        lexical_query,
                        effective_bm25_top_k,
                    )
                    vector_future = executor.submit(
                        self._run_vector_search,
                        vector_runner,
                        prepared.dense_query,
                        effective_vector_top_k,
                    )
                    bm25_results, bm25_ms = bm25_future.result()
                    vector_results, vector_ms = vector_future.result()
            else:
                bm25_results, bm25_ms = self._run_bm25_search(
                    self.bm25_retriever,
                    lexical_query,
                    effective_bm25_top_k,
                )
                vector_results, vector_ms = self._run_vector_search(
                    self.vector_retriever,
                    prepared.dense_query,
                    effective_vector_top_k,
                )

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
            apply_mmr_in_merge = False
            merged = self.merger.merge(
                bm25_results,
                vector_results,
                self.config,
                apply_mmr=apply_mmr_in_merge,
            )
            merge_ms = (time.perf_counter() - merge_start) * 1000
            count_after_merge = len(merged)

            # Post-merge gate: adaptive knee or static cap
            knee_gate_result = None
            if plan_b_active and self.config.adaptive_seed_enabled:
                knee_gate_result = hybrid_knee_gate(
                    merged,
                    min_k=self.config.adaptive_seed_min_k,
                    max_k=self.config.adaptive_seed_max_k,
                    relative_drop_threshold=self.config.adaptive_seed_drop_threshold,
                )
                merged = knee_gate_result.candidates
            elif plan_b_active:
                # Stabilization invariant: no static post-merge caps in Plan B.
                if effective_post_merge_candidates and len(merged) > effective_post_merge_candidates:
                    logger.info(
                        "[RETRIEVAL] static post-merge cap ignored under Plan B stabilization (configured=%d current=%d)",
                        effective_post_merge_candidates,
                        len(merged),
                    )
            elif effective_post_merge_candidates and len(merged) > effective_post_merge_candidates:
                merged = merged[:effective_post_merge_candidates]
            count_after_cap = len(merged)
            
            # MMR diversity reranking BEFORE dedup
            # (so MMR preserves diversity-valuable candidates that dedup would remove)
            if not apply_mmr_in_merge:
                mmr_start = time.perf_counter()
                merged = self.merger.apply_mmr(merged, self.config)
                mmr_ms = (time.perf_counter() - mmr_start) * 1000
            else:
                mmr_ms = 0.0
            count_after_mmr = len(merged)

            # Hierarchical deduplication AFTER MMR
            if plan_b_active and self.config.hierarchical_dedup_enabled:
                merged = deduplicate_hierarchical(merged, intent=resolved_intent)
            count_after_dedup = len(merged)
            
            # =================================================================
            # Plan B: Step 3 — Intent-Driven Granularity Boosting
            # =================================================================
            if plan_b_active and self.config.granularity_boost_enabled:
                gran_start = time.perf_counter()
                merged = self._apply_granularity_boost(merged, resolved_intent)
                granularity_ms = (time.perf_counter() - gran_start) * 1000
            else:
                granularity_ms = 0.0

            # Intent-driven granularity mixing
            if plan_b_active and self.config.granularity_mixing_enabled:
                merged = apply_granularity_mix(
                    merged,
                    resolved_intent,
                    self.config.granularity_mixing_profiles,
                )
            count_after_granularity = len(merged)

            # 4. Structural expansion
            if self.config.expansion_enabled:
                # Plan B: Step 4 — Graph Stitch first, then legacy expansion
                if plan_b_active and self._graph_stitch_expander:
                    gs_start = time.perf_counter()
                    merged = self._graph_stitch_expander.expand(merged, query)
                    graph_stitch_ms = (time.perf_counter() - gs_start) * 1000
                else:
                    graph_stitch_ms = 0.0
                count_after_graph_stitch = len(merged)
                
                # Legacy expansion (callgraph-based, cached at init)
                callgraph = self._callgraph_cache
                exp_start = time.perf_counter()
                merged = self.expander.expand(merged, query, callgraph, self.config)
                expansion_ms = (time.perf_counter() - exp_start) * 1000
            else:
                graph_stitch_ms = 0.0
                expansion_ms = 0.0
                count_after_graph_stitch = len(merged)
            count_after_expansion = len(merged)

            # 5. Precision recovery (missing entity detection)
            pr_start = time.perf_counter()
            merged = self.precision_recovery.recover(
                merged,
                query,
                self.config,
                max_additions=self.config.precision_recovery_max_additions,
            )
            precision_ms = (time.perf_counter() - pr_start) * 1000
            precision_metrics = getattr(self.precision_recovery, "last_metrics", {})
            count_after_precision = len(merged)
            if precision_metrics.get("precision_recovery_added", 0):
                logger.info(
                    "[PRECISION_RECOVERY_QUERY] query_id=%s added=%s cap=%s conf_mean=%s",
                    query_id,
                    precision_metrics.get("precision_recovery_added"),
                    precision_metrics.get("precision_recovery_cap"),
                    precision_metrics.get("precision_recovery_conf_mean"),
                )

            # 6. Budget-aware selection + top-k
            # When adaptive_seed_enabled, skip retrieval-level budget gate
            # (the submodular packer in context layer handles allocation)
            budget_used = None
            budget_effective = None
            if plan_b_active and self.config.budget_aware_selection and not self.config.adaptive_seed_enabled:
                merged = sorted(merged, key=_candidate_order_key)
                merged, budget_tracker = select_candidates_with_budget(
                    merged,
                    total_budget=self.config.context_budget,
                    reserve=self.config.budget_reserve,
                )
                budget_used = budget_tracker.used
                budget_effective = budget_tracker.effective_budget

            final_candidates = merged[:effective_output_top_k]
            total_ms = (time.perf_counter() - t0) * 1000

            # Stage trace (Tier 3 instrumentation)
            retrieval_stage_trace = {
                "bm25_raw": len(bm25_results),
                "vector_raw": len(vector_results),
                "after_merge": count_after_merge,
                "after_cap": count_after_cap,
                "after_dedup": count_after_dedup,
                "after_mmr": count_after_mmr,
                "after_granularity": count_after_granularity,
                "after_graph_stitch": count_after_graph_stitch,
                "after_expansion": count_after_expansion,
                "after_precision": count_after_precision,
                "final_output": len(final_candidates),
            }

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
                    "search_mode": search_mode,
                    "vector_calibration_mode": self.config.vector_calibration_mode,
                    "static_ceiling_mode": static_ceiling_mode,
                    "effective_bm25_top_k": effective_bm25_top_k,
                    "effective_vector_top_k": effective_vector_top_k,
                    "effective_post_merge_candidates": effective_post_merge_candidates,
                    "effective_output_top_k": effective_output_top_k,
                    "adaptive_k": requested_k,
                    "resolved_intent": resolved_intent.value,
                    "intent_source": intent_source,
                    "intent_rule": intent_rule,
                    "query_expansion_enabled": self.config.query_expansion_enabled,
                    "query_expansion_terms": list(prepared.lexical_expansion_terms),
                    "query_expansion_term_count": len(prepared.lexical_expansion_terms),
                    "prep_ms": round(prep_ms, 2),
                    "bm25_ms": round(bm25_ms, 2) if bm25_ms is not None else None,
                    "vector_ms": round(vector_ms, 2) if vector_ms is not None else None,
                    "merge_ms": round(merge_ms, 2),
                    "mmr_ms": round(mmr_ms, 2),
                    "granularity_ms": round(granularity_ms, 2),
                    "graph_stitch_ms": round(graph_stitch_ms, 2),
                    "expansion_ms": round(expansion_ms, 2),
                    "precision_ms": round(precision_ms, 2),
                    "precision_recovery_added": precision_metrics.get("precision_recovery_added"),
                    "precision_recovery_cap": precision_metrics.get("precision_recovery_cap"),
                    "precision_recovery_identifiers": precision_metrics.get("precision_recovery_identifiers"),
                    "precision_recovery_conf_min": precision_metrics.get("precision_recovery_conf_min"),
                    "precision_recovery_conf_max": precision_metrics.get("precision_recovery_conf_max"),
                    "precision_recovery_conf_mean": precision_metrics.get("precision_recovery_conf_mean"),
                    "total_ms": round(total_ms, 2),
                    "mmr_candidates": getattr(self.merger, "last_metrics", {}).get("mmr_candidates"),
                    "mmr_emb_ms": getattr(self.merger, "last_metrics", {}).get("mmr_emb_ms"),
                    "mmr_ms_merger": getattr(self.merger, "last_metrics", {}).get("mmr_ms"),
                    "mmr_error": getattr(self.merger, "last_metrics", {}).get("mmr_error"),
                    "budget_used_tokens": budget_used,
                    "budget_effective_tokens": budget_effective,
                    "retrieval_stage_trace": retrieval_stage_trace,
                    "graph_stitch_status": self._graph_stitch_status,
                    "graph_stitch_status_detail": self._graph_stitch_status_detail,
                    # Tier 3B: adaptive seed gate telemetry
                    "adaptive_seed_enabled": self.config.adaptive_seed_enabled,
                    "knee_gate": {
                        "knee_position": knee_gate_result.knee_position if knee_gate_result else None,
                        "pre_knee_count": knee_gate_result.pre_knee_count if knee_gate_result else None,
                        "post_knee_count": knee_gate_result.post_knee_count if knee_gate_result else None,
                    } if knee_gate_result else None,
                },
            )

        except Exception as e:
            logger.error(f"Retrieval pipeline failed: {e}")
            return RetrievalResult(
                candidates=[],
                query_id=query_id,
                metadata={"error": str(e)},
            )

    def retrieve_focused_candidates(
        self,
        query: str,
        focused_queries: list[str],
        intent: Intent = Intent.UNKNOWN,
        top_k: int = 20,
    ) -> list:
        """
        Targeted retrieval surface for unresolved-claim recovery.

        This is read-only and query-agnostic: it runs lightweight branch retrieval
        for each focused query and returns deduplicated candidates by doc_id.
        """
        if not focused_queries:
            return []

        all_candidates = []
        for fq in focused_queries:
            try:
                prepared = self.preparer.prepare(fq, intent)
                lexical_query = " ".join(prepared.lexical_terms)
                bm25_results, _ = self._run_bm25_search(
                    self.bm25_retriever,
                    lexical_query,
                    max(1, int(top_k)),
                )
                vector_results, _ = self._run_vector_search(
                    self.vector_retriever,
                    prepared.dense_query,
                    max(1, int(top_k)),
                )
                merged = self.merger.merge(
                    bm25_results,
                    vector_results,
                    self.config,
                    apply_mmr=False,
                )
                all_candidates.extend(merged[: max(1, int(top_k))])
            except Exception as exc:
                logger.warning("[RETRIEVAL] focused query failed: %s", exc)
                continue

        # Deterministic dedup by doc_id, retaining highest hybrid score.
        by_id = {}
        for cand in all_candidates:
            prev = by_id.get(cand.doc_id)
            if prev is None or float(cand.hybrid_score) > float(prev.hybrid_score):
                by_id[cand.doc_id] = cand
        out = list(by_id.values())
        out.sort(key=_candidate_order_key)
        return out

    def _validate_parallel_adapter_safety(self) -> bool:
        """Return True only when both retrievers explicitly declare thread-safe search."""
        bm25_safe = bool(
            hasattr(self.bm25_retriever, "supports_thread_safe_search")
            and self.bm25_retriever.supports_thread_safe_search()
        )
        vector_safe = bool(
            hasattr(self.vector_retriever, "supports_thread_safe_search")
            and self.vector_retriever.supports_thread_safe_search()
        )
        logger.info(
            "[PARALLEL_SEARCH] bm25_thread_safe=%s vector_thread_safe=%s",
            bm25_safe,
            vector_safe,
        )
        return bm25_safe and vector_safe

    def _build_branch_local_search_runners(self):
        """Build isolated retriever instances for parallel branch execution."""
        bm25_runner = (
            self.bm25_retriever.clone_for_search()
            if hasattr(self.bm25_retriever, "clone_for_search")
            else BM25Retriever(self._bm25_index_path, duckdb_path=self.duckdb_path)
        )
        vector_runner = (
            self.vector_retriever.clone_for_search()
            if hasattr(self.vector_retriever, "clone_for_search")
            else VectorRetriever(
                self._vector_db_path,
                self.embedder,
                duckdb_path=self.duckdb_path,
                calibration_mode=self.config.vector_calibration_mode,
            )
        )
        return bm25_runner, vector_runner

    def _resolve_parallel_search_runners(self):
        """
        Resolve retrievers for parallel search.

        If shared retrievers are not explicitly thread-safe, use branch-local clones.
        """
        if self._validate_parallel_adapter_safety():
            return self.bm25_retriever, self.vector_retriever, "parallel_shared"
        bm25_runner, vector_runner = self._build_branch_local_search_runners()
        return bm25_runner, vector_runner, "parallel_branch_local"

    def _run_bm25_search(self, retriever, query: str, top_k: int):
        """Run BM25 search with per-branch timing and failure isolation."""
        try:
            start = time.perf_counter()
            results = retriever.search(query, top_k)
            return results, (time.perf_counter() - start) * 1000
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return [], None

    def _run_vector_search(self, retriever, query: str, top_k: int):
        """Run vector search with per-branch timing and failure isolation."""
        try:
            start = time.perf_counter()
            results = retriever.search(query, top_k)
            return results, (time.perf_counter() - start) * 1000
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return [], None

    def _resolve_static_ceiling_limits(
        self,
        top_k: int,
        requested_branch_k: int | None = None,
    ) -> tuple[int, int, int, int, str]:
        """
        Resolve deterministic static retrieval ceilings for Phase-A experimentation.
        A4: When static experiment is off, use requested_branch_k (adaptive k) if provided.
        """
        bm25_top_k = self.config.bm25_top_k
        vector_top_k = self.config.vector_top_k
        post_merge = self.config.post_merge_candidates
        output_top_k = top_k

        if not self.config.static_ceiling_experiment_enabled:
            if requested_branch_k is not None:
                bm25_top_k = max(bm25_top_k, requested_branch_k)
                vector_top_k = max(vector_top_k, requested_branch_k)
                output_top_k = max(top_k, requested_branch_k)
            return bm25_top_k, vector_top_k, post_merge, output_top_k, "baseline"

        bm25_top_k = max(1, bm25_top_k * self.config.static_ceiling_branch_multiplier)
        vector_top_k = max(1, vector_top_k * self.config.static_ceiling_branch_multiplier)
        if post_merge > 0:
            post_merge = max(1, post_merge * self.config.static_ceiling_post_merge_multiplier)
        output_top_k = max(1, top_k * self.config.static_ceiling_output_multiplier)
        return bm25_top_k, vector_top_k, post_merge, output_top_k, "static_ceiling_v1"
    
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

