"""Context assembly pipeline orchestrator."""

import logging
import re
import uuid
from collections import Counter
from typing import Optional

from homllm.context.assembler import BlockAssembler
from homllm.context.budget import TokenBudgetManager
from homllm.context.deduper import ContextDeduplicator
from homllm.context.interfaces import (
    BudgetConfig,
    ContextArtifact,
    ContextConfig,
    ScoredBlock,
)
from homllm.context.scorer import ContextBlockScorer
from homllm.context.stitcher import ContextStitcher
from homllm.context.submodular_packer import PackerConfig, submodular_pack
from homllm.ranking.interfaces import DebugTrace, RankingOutput

logger = logging.getLogger(__name__)


class ContextPipeline:
    """
    Main context assembly pipeline.
    
    Flow: Ranked Candidates → Enrich → Missing-Ref Detect → Score → Dedup → Budget → Compress → Order → Stitch → Output
    
    Invariants:
    - CTX-001: Same inputs + config → same context artifact
    - CTX-002: Token budget is strict upper bound
    - CTX-003: Provenance for every included block
    - CTX-004: No hardcoded structural rules
    - CTX-005: Deterministic block ordering
    """

    def __init__(
        self,
        config: ContextConfig,
        embedder: Optional[object] = None,
        tokenizer: Optional[object] = None,
        callgraph: Optional[dict] = None,
    ):
        """
        Initialize context pipeline.
        
        Args:
            config: Context configuration
            embedder: Embedder for coherence scoring (optional)
            tokenizer: Tokenizer for exact token counting (optional)
            callgraph: Call graph dict (symbol_id → [callee_ids]) for coherence
        """
        self.config = config
        self.callgraph = callgraph or {}
        # Extract tokenizer from embedder if not explicitly provided.
        # This ensures TokenBudgetManager uses accurate token counts
        # instead of the len//4 fallback.
        if tokenizer is None and embedder is not None:
            tokenizer = getattr(embedder, "tokenizer", None)
        self.tokenizer = tokenizer

        self.assembler = BlockAssembler()
        self.scorer = ContextBlockScorer(embedder, config)
        self.deduplicator = ContextDeduplicator()
        self.budget_manager = TokenBudgetManager()
        self.stitcher = ContextStitcher(callgraph=self.callgraph)

    def assemble(
        self,
        ranking_output: RankingOutput,
        query: str,
        query_id: Optional[str] = None,
        unresolved_claim_hints: Optional[list[str]] = None,
    ) -> ContextArtifact:
        """
        Execute context assembly pipeline.
        
        Args:
            ranking_output: Output from ranking layer
            query: Original query
            query_id: Query ID (default: generate UUID)
        
        Returns:
            ContextArtifact with stitched context and metadata
        
        Guaranteates:
        - Deterministic for same inputs
        - Token budget is strict upper bound
        - Provenance tracked for all blocks
        """
        if query_id is None:
            query_id = str(uuid.uuid4())

        try:
            # 1. Assemble blocks from ranked candidates
            blocks = self.assembler.assemble(list(ranking_output.ranked_candidates))
            ranking_surface_lock_enabled = bool(
                getattr(self.config, "ranking_surface_lock_enabled", True)
            )

            if not blocks:
                # Zero candidates - return empty context
                return ContextArtifact(
                    query_id=query_id,
                    context_text="",
                    blocks=tuple(),
                    token_budget=self.config.max_tokens,
                    used_tokens=0,
                    provenance={
                        "query": query,
                        "query_text": query,
                        "unresolved_claim_hints": list(unresolved_claim_hints or []),
                        "ranking_surface_lock_enabled": ranking_surface_lock_enabled,
                        "ranking_order_preserved": True,
                        "context_reorder_count": 0,
                    },
                    explain_trace=tuple(["No candidates found"]),
                )

            # Context synthesis profile (query-agnostic) used only for budget modulation.
            # This does not re-rank semantics; it only prevents single-block budget capture.
            from homllm.context.synthesis_profile import compute_context_synthesis_profile
            from homllm.context.integration_controller import (
                compute_context_integration_profile,
            )

            debug_trace_map = {
                trace.candidate_id: trace for trace in ranking_output.debug_traces
            }
            semantic_scores = {}
            for cand in ranking_output.ranked_candidates:
                trace = debug_trace_map.get(cand.doc_id)
                if trace:
                    semantic_scores[cand.doc_id] = trace.base_score + trace.rerank_score
                else:
                    semantic_scores[cand.doc_id] = 0.0

            def _file_hist(items) -> dict[str, int]:
                counter = Counter()
                for it in items:
                    file_path = getattr(it, "file", None)
                    if file_path:
                        counter[str(file_path)] += 1
                return dict(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))

            synthesis_profile = compute_context_synthesis_profile(
                query=query,
                candidates=ranking_output.ranked_candidates,
                semantic_scores=semantic_scores,
            )

            # 2. Build context scored blocks.
            # Under authority lock, this is ranking-trace passthrough (no context rescoring).
            if ranking_surface_lock_enabled:
                scored_blocks = self._build_rank_locked_scored_blocks(
                    blocks, debug_trace_map
                )
            else:
                scored_blocks = self.scorer.score(
                    blocks, query, [], debug_trace_map
                )

            # 2b. Tier 2: Post-lock coherence refinement.
            # Adjusts mid-range blocks only (top-N protected). Deterministic.
            pre_coherence_ids = [sb.block.block_id for sb in scored_blocks]
            scored_blocks = self.scorer.compute_coherence_refinement(
                scored_blocks, self.callgraph, self.config
            )
            post_coherence_ids = [sb.block.block_id for sb in scored_blocks]
            # Integrity: top-N must be unchanged
            protect_n = getattr(self.config, "coherence_protect_top_n", 3)
            if pre_coherence_ids[:protect_n] != post_coherence_ids[:protect_n]:
                logger.error(
                    "COHERENCE_TOP_N_VIOLATION: top-%d changed, reverting", protect_n
                )
                scored_blocks = self.scorer.compute_coherence_refinement(
                    scored_blocks, {}, self.config  # Empty callgraph = no-op
                )

            # Context integration profile: set-level geometry from scored blocks (ranking order).
            # Used only to modulate budget allocation while preserving order.
            integration_profile = compute_context_integration_profile(
                query=query,
                ranked_blocks=scored_blocks,
                top_n=20,
            )

            stage_counts = {
                "ranked_candidates": len(ranking_output.ranked_candidates),
                "assembled_blocks": len(blocks),
                "scored_blocks": len(scored_blocks),
            }

            stage_file_histograms = {
                "assembled": _file_hist(blocks),
                "scored": _file_hist([sb.block for sb in scored_blocks]),
            }

            scored_order_top10 = [
                {
                    "block_id": sb.block.block_id,
                    "file": sb.block.file,
                    "final_score": sb.final_score,
                    "semantic_score": sb.semantic_score,
                    "name_score": sb.name_score,
                }
                for sb in scored_blocks[:10]
            ]

            # 3. Deduplicate
            unique_blocks = self.deduplicator.deduplicate(
                [sb.block for sb in scored_blocks]
            )
            stage_counts["dedup_blocks"] = len(unique_blocks)
            stage_file_histograms["dedup"] = _file_hist(unique_blocks)
            # Rebuild scored blocks with unique blocks only
            unique_ids = {b.block_id for b in unique_blocks}
            unique_scored = [
                sb for sb in scored_blocks if sb.block.block_id in unique_ids
            ]

            # 4. Budget allocation (standard or submodular packer)
            effective_context_budget = (
                self.config.max_tokens - self.config.generation_reserve_tokens
            )
            context_max_tokens_effective = self.config.max_tokens
            submodular_telemetry = None
            dynamic_budget_trace = None
            utilization_diagnostic_override = None
            ranking_order_override = False

            if getattr(self.config, "submodular_packer_enabled", False):
                # Tier 3B: Submodular context packing
                # Build graph edges from callgraph for graph_gain
                graph_edges: dict[str, set[str]] = {}
                submodular_graph_weight = float(
                    getattr(self.config, "submodular_w_graph", 0.20) or 0.0
                )
                graph_isolation_active = submodular_graph_weight <= 0.0
                graph_isolation_reason = "weight_zero" if graph_isolation_active else "weight_nonzero"
                if not graph_isolation_active and self.callgraph:
                    # Support both legacy {"edges":[...]} and runtime map {caller:[callee,...]}.
                    if isinstance(self.callgraph.get("edges"), list):
                        for edge in self.callgraph.get("edges", []):
                            caller = edge.get("caller_id", "")
                            callee = edge.get("callee_id", "")
                            if caller and callee:
                                graph_edges.setdefault(caller, set()).add(callee)
                                graph_edges.setdefault(callee, set()).add(caller)
                    else:
                        for caller, callees in sorted(self.callgraph.items()):
                            if not caller or not isinstance(callees, list):
                                continue
                            for callee in sorted(callees):
                                if callee:
                                    graph_edges.setdefault(caller, set()).add(callee)
                                    graph_edges.setdefault(callee, set()).add(caller)

                packer_config_kwargs = {
                    "w_rrf": getattr(self.config, "submodular_w_rrf", 0.40),
                    "w_novelty": getattr(self.config, "submodular_w_novelty", 0.20),
                    "w_graph": getattr(self.config, "submodular_w_graph", 0.20),
                    "w_concept": getattr(self.config, "submodular_w_concept", 0.20),
                    "min_density_epsilon": getattr(
                        self.config, "submodular_min_density_epsilon", 0.001
                    ),
                    "noise_guard_enabled": getattr(
                        self.config, "submodular_noise_guard_enabled", False
                    ),
                    "noise_guard_min_file_ratio": getattr(
                        self.config, "submodular_noise_guard_min_file_ratio", 0.60
                    ),
                    "noise_guard_rrf_ratio_threshold": getattr(
                        self.config, "submodular_noise_guard_rrf_ratio_threshold", 0.85
                    ),
                    "novelty_scaling": getattr(
                        self.config, "submodular_novelty_scaling", "none"
                    ),
                    "enabled": True,
                }

                def _run_packer(max_tokens: int):
                    packer_config = PackerConfig(
                        max_tokens=max_tokens,
                        **packer_config_kwargs,
                    )
                    pack_result = submodular_pack(
                        unique_scored, query, packer_config, graph_edges,
                        tokenizer=self.tokenizer,
                    )
                    # Re-sort to preserve original ranking order (packer selects WHICH,
                    # ranking controls ORDER — ranking surface lock invariant)
                    selected_ids = {sb.block.block_id for sb in pack_result.selected}
                    ranking_positions = {
                        str(getattr(c, "doc_id", "")): idx
                        for idx, c in enumerate(ranking_output.ranked_candidates)
                    }
                    ordered_selected = sorted(
                        (sb for sb in unique_scored if sb.block.block_id in selected_ids),
                        key=lambda sb: ranking_positions.get(sb.block.block_id, 10**9),
                    )
                    # Wrap into AllocatedBlock (stitcher expects truncated_content)
                    from homllm.context.interfaces import AllocatedBlock
                    allocated_blocks = []
                    for sb in ordered_selected:
                        est_tokens = self._estimate_tokens_with_tokenizer(
                            sb.block.content
                        )
                        allocated_blocks.append(
                            AllocatedBlock(
                                block=sb.block,
                                allocated_tokens=est_tokens,
                                truncated_content=sb.block.content or "",
                            )
                        )
                    return allocated_blocks, pack_result

                allocated_blocks, pack_result = _run_packer(effective_context_budget)
                submodular_telemetry = pack_result.telemetry

                if getattr(self.config, "dynamic_budget_enabled", False):
                    base_budget = int(effective_context_budget)
                    max_extra = int(
                        getattr(self.config, "dynamic_budget_max_extra_tokens", 0) or 0
                    )
                    max_budget = base_budget + max_extra
                    step_tokens = int(
                        getattr(self.config, "dynamic_budget_step_tokens", 0) or 0
                    )
                    max_expansions = int(
                        getattr(self.config, "dynamic_budget_max_expansions", 0) or 0
                    )
                    trigger_used_pct = float(
                        getattr(self.config, "dynamic_budget_trigger_used_pct", 0.80) or 0.80
                    )
                    min_budget_limited_tokens = int(
                        getattr(self.config, "dynamic_budget_min_budget_limited_tokens", 128) or 128
                    )
                    safety_margin_tokens = int(
                        getattr(self.config, "dynamic_budget_safety_margin_tokens", 192) or 192
                    )
                    tail_density_ratio_trigger = float(
                        getattr(self.config, "dynamic_budget_tail_density_ratio_trigger", 0.65) or 0.65
                    )

                    budget_limit_threshold = max(min_budget_limited_tokens, safety_margin_tokens)
                    dynamic_budget_trace = {
                        "enabled": True,
                        "triggered": False,
                        "base_budget": base_budget,
                        "current_budget": base_budget,
                        "max_budget": max_budget,
                        "step_tokens": step_tokens,
                        "max_expansions": max_expansions,
                        "trigger_used_pct": trigger_used_pct,
                        "budget_limit_threshold": budget_limit_threshold,
                        "tail_density_ratio_trigger": tail_density_ratio_trigger,
                        "decisions": [],
                        "expansions": [],
                    }

                    expansions = 0
                    current_budget = base_budget
                    current_pack = pack_result
                    current_blocks = allocated_blocks

                    while expansions < max_expansions:
                        decision = self._dynamic_budget_decision(
                            telemetry=current_pack.telemetry,
                            current_budget=current_budget,
                            trigger_used_pct=trigger_used_pct,
                            budget_limit_threshold=budget_limit_threshold,
                            tail_density_ratio_trigger=tail_density_ratio_trigger,
                        )
                        dynamic_budget_trace["decisions"].append(decision)
                        if not decision.get("expand"):
                            break

                        if step_tokens <= 0:
                            dynamic_budget_trace["decisions"][-1]["expand"] = False
                            dynamic_budget_trace["decisions"][-1]["reason"] = "step_tokens_disabled"
                            break

                        next_budget = min(current_budget + step_tokens, max_budget)
                        if next_budget <= current_budget:
                            dynamic_budget_trace["decisions"][-1]["expand"] = False
                            dynamic_budget_trace["decisions"][-1]["reason"] = "max_budget_reached"
                            break

                        next_blocks, next_pack = _run_packer(next_budget)
                        expansion_entry = {
                            "from_budget": current_budget,
                            "to_budget": next_budget,
                            "used_tokens": int(next_pack.telemetry.get("total_tokens_used", 0) or 0),
                            "token_utilization": float(next_pack.telemetry.get("token_utilization", 0.0) or 0.0),
                            "stop_reason": next_pack.telemetry.get("stop_reason"),
                            "tail_density_ratio": float(decision.get("tail_density_ratio", 0.0) or 0.0),
                        }
                        dynamic_budget_trace["expansions"].append(expansion_entry)

                        current_budget = next_budget
                        current_pack = next_pack
                        current_blocks = next_blocks
                        expansions += 1

                    if expansions > 0:
                        dynamic_budget_trace["triggered"] = True
                        dynamic_budget_trace["current_budget"] = current_budget
                        dynamic_budget_trace["final_used_tokens"] = int(
                            current_pack.telemetry.get("total_tokens_used", 0) or 0
                        )
                        dynamic_budget_trace["final_utilization"] = float(
                            current_pack.telemetry.get("token_utilization", 0.0) or 0.0
                        )
                        dynamic_budget_trace["final_stop_reason"] = current_pack.telemetry.get("stop_reason")
                        effective_context_budget = current_budget
                        context_max_tokens_effective = (
                            effective_context_budget + self.config.generation_reserve_tokens
                        )
                        allocated_blocks = current_blocks
                        submodular_telemetry = current_pack.telemetry
                    else:
                        dynamic_budget_trace["current_budget"] = current_budget
                if isinstance(submodular_telemetry, dict):
                    submodular_telemetry["graph_isolation"] = {
                        "active": graph_isolation_active,
                        "reason": graph_isolation_reason,
                        "graph_weight": submodular_graph_weight,
                        "graph_edge_count_used": sum(len(v) for v in graph_edges.values()),
                    }
                if isinstance(submodular_telemetry, dict):
                    submodular_used_tokens = sum(
                        int(ab.allocated_tokens) for ab in allocated_blocks
                    )
                    utilization_diagnostic_override = {
                        "classification": "Submodular",
                        "final_tokens": submodular_used_tokens,
                        "token_budget": effective_context_budget,
                        "utilization_pct": round(
                            100 * submodular_used_tokens / max(1, effective_context_budget), 2
                        ),
                        "unused_tokens": max(0, effective_context_budget - submodular_used_tokens),
                        "stop_reason": submodular_telemetry.get("stop_reason"),
                    }
                if getattr(self.config, "ranking_surface_lock_enabled", False):
                    ranking_positions = {
                        str(getattr(c, "doc_id", "")): idx
                        for idx, c in enumerate(ranking_output.ranked_candidates)
                    }
                    allocated_ids = [ab.block.block_id for ab in allocated_blocks]
                    if allocated_ids and all(bid in ranking_positions for bid in allocated_ids):
                        ranking_order_override = True
            else:
                # Standard budget allocation
                budget_config = BudgetConfig(
                    max_tokens=effective_context_budget,
                    budget_mode=self.config.budget_mode,
                    structural_priority_multiplier=self.config.structural_priority_multiplier,
                )

                allocated_blocks = self.budget_manager.allocate(
                    unique_scored,
                    {
                        "query": query,
                        "synthesis_score": synthesis_profile.synthesis_score,
                        "synthesis_components": {
                            "concept_density": synthesis_profile.concept_density,
                            "file_dispersion": synthesis_profile.file_dispersion,
                            "semantic_entropy": synthesis_profile.semantic_entropy,
                            "retrieval_disagreement": synthesis_profile.retrieval_disagreement,
                        },
                        "integration_pressure": integration_profile.integration_pressure,
                        "distinct_files_topn": max(1, int(round(integration_profile.file_dispersion * min(20, len(unique_scored))))),
                    },
                    budget_config,
                    self.tokenizer,
                    preserve_order=True,
                )
            stage_counts["allocated_blocks"] = len(allocated_blocks)
            stage_file_histograms["allocated"] = _file_hist([ab.block for ab in allocated_blocks])

            # Claim-gain epsilon swap (post-packer, low-risk tie-break).
            claim_gain_swap_trace = {"active": False, "reason": "disabled", "swaps_applied": 0}
            if getattr(self.config, "claim_gain_swap_enabled", False):
                allocated_blocks, claim_gain_swap_trace = self._apply_claim_gain_epsilon_swap(
                    allocated_blocks=allocated_blocks,
                    ranked_scored_blocks=unique_scored,
                    effective_context_budget=effective_context_budget,
                    unresolved_claim_hints=unresolved_claim_hints or [],
                )
                stage_counts["claim_gain_swapped_blocks"] = len(allocated_blocks)
                stage_file_histograms["claim_gain_swapped"] = _file_hist(
                    [ab.block for ab in allocated_blocks]
                )

            unresolved_evidence_injection_trace = {
                "active": False,
                "reason": "disabled",
                "candidate_count_considered": 0,
                "blocks_injected": 0,
                "replaced_block_ids": [],
                "injected_block_ids": [],
                "tokens_before": sum(int(ab.allocated_tokens) for ab in allocated_blocks),
                "tokens_after": sum(int(ab.allocated_tokens) for ab in allocated_blocks),
                "claim_gain_delta_total": 0.0,
            }
            if getattr(self.config, "unresolved_evidence_injection_enabled", False):
                allocated_blocks, unresolved_evidence_injection_trace = (
                    self._apply_unresolved_evidence_injection(
                        allocated_blocks=allocated_blocks,
                        ranked_scored_blocks=unique_scored,
                        effective_context_budget=effective_context_budget,
                        unresolved_claim_hints=unresolved_claim_hints or [],
                        query=query,
                    )
                )
                stage_counts["unresolved_evidence_injected_blocks"] = len(allocated_blocks)
                stage_file_histograms["unresolved_evidence_injected"] = _file_hist(
                    [ab.block for ab in allocated_blocks]
                )

            # Tier 3C: Conservative precision filter for explicit-identifier queries.
            precision_filter_trace = None
            if getattr(self.config, "precision_filter_enabled", False):
                allocated_blocks, precision_filter_trace = self._apply_precision_filter(
                    allocated_blocks=allocated_blocks,
                    scored_map={sb.block.block_id: sb for sb in unique_scored},
                    query=query,
                )
                stage_counts["precision_filtered_blocks"] = len(allocated_blocks)
                stage_file_histograms["precision_filtered"] = _file_hist(
                    [ab.block for ab in allocated_blocks]
                )

            # Tier 3C: Sparse-context backfill (conservative).
            # If context is materially under-filled, append next-ranked unseen blocks.
            sparse_backfill_trace = None
            if getattr(self.config, "sparse_backfill_enabled", False):
                allocated_blocks, sparse_backfill_trace = self._apply_sparse_backfill(
                    allocated_blocks=allocated_blocks,
                    ranked_scored_blocks=unique_scored,
                    effective_context_budget=effective_context_budget,
                )
                stage_counts["sparse_backfill_blocks"] = len(allocated_blocks)
                stage_file_histograms["sparse_backfill"] = _file_hist(
                    [ab.block for ab in allocated_blocks]
                )

            budget_guard_trace = self._apply_final_budget_guard(
                allocated_blocks=allocated_blocks,
                effective_context_budget=effective_context_budget,
            )
            if budget_guard_trace.get("active"):
                removed_ids = set(budget_guard_trace.get("removed_block_ids", []) or [])
                allocated_blocks = [
                    ab for ab in allocated_blocks if ab.block.block_id not in removed_ids
                ]
            stage_counts["budget_guard_blocks"] = len(allocated_blocks)
            stage_file_histograms["budget_guard"] = _file_hist(
                [ab.block for ab in allocated_blocks]
            )

            low_value_suppression_trace = {"active": False, "reason": "disabled"}
            if getattr(self.config, "low_value_suppression_enabled", False):
                allocated_blocks, low_value_suppression_trace = self._apply_low_value_suppression(
                    allocated_blocks
                )
                stage_counts["low_value_suppression_blocks"] = len(allocated_blocks)
                stage_file_histograms["low_value_suppression"] = _file_hist(
                    [ab.block for ab in allocated_blocks]
                )

            ranking_ids = [str(getattr(c, "doc_id", "")) for c in ranking_output.ranked_candidates]
            allocated_ids = [ab.block.block_id for ab in allocated_blocks]
            context_reorder_count = self._count_reorders(ranking_ids, allocated_ids)
            ranking_order_preserved = context_reorder_count == 0
            original_reorder_count = context_reorder_count
            ranking_authority_fallback_trace = {
                "active": False,
                "reason": None,
                "original_reorder_count": original_reorder_count,
            }
            if ranking_order_override:
                context_reorder_count = 0
                ranking_order_preserved = True

            coherence_active = getattr(self.config, "coherence_enabled", False)
            if ranking_surface_lock_enabled and not ranking_order_preserved:
                if coherence_active:
                    # Tier 2: Allow mid-range reorders from coherence refinement,
                    # but verify top-N blocks maintain relative order.
                    top_n = getattr(self.config, "coherence_protect_top_n", 3)
                    top_ranking_ids = ranking_ids[:top_n]
                    top_allocated_ids = [
                        aid for aid in allocated_ids if aid in set(top_ranking_ids)
                    ]
                    top_reorders = self._count_reorders(top_ranking_ids, top_allocated_ids)
                    if top_reorders > 0:
                        logger.warning(
                            "[CONTEXT] ranking authority violation on top-%d (reorders=%d); "
                            "falling back to strict rank-ordered budget allocation",
                            top_n,
                            top_reorders,
                        )
                        allocated_blocks = self._fallback_rank_locked_allocation(
                            ranked_scored_blocks=unique_scored,
                            effective_context_budget=effective_context_budget,
                            query=query,
                        )
                        allocated_ids = [ab.block.block_id for ab in allocated_blocks]
                        context_reorder_count = self._count_reorders(ranking_ids, allocated_ids)
                        ranking_order_preserved = context_reorder_count == 0
                        ranking_authority_fallback_trace = {
                            "active": True,
                            "reason": f"top_{top_n}_reorder_count={top_reorders}",
                            "original_reorder_count": original_reorder_count,
                        }
                    # Log coherence-driven reorders (allowed)
                    if not ranking_authority_fallback_trace["active"]:
                        logger.info(
                            "[CONTEXT] coherence mid-range reorders=%d (allowed, top-%d protected)",
                            context_reorder_count, top_n,
                        )
                else:
                    logger.warning(
                        "[CONTEXT] ranking authority violation (reorders=%d); "
                        "falling back to strict rank-ordered budget allocation",
                        context_reorder_count,
                    )
                    allocated_blocks = self._fallback_rank_locked_allocation(
                        ranked_scored_blocks=unique_scored,
                        effective_context_budget=effective_context_budget,
                        query=query,
                    )
                    allocated_ids = [ab.block.block_id for ab in allocated_blocks]
                    context_reorder_count = self._count_reorders(ranking_ids, allocated_ids)
                    ranking_order_preserved = context_reorder_count == 0
                    ranking_authority_fallback_trace = {
                        "active": True,
                        "reason": "context_reorder_count_violation",
                        "original_reorder_count": original_reorder_count,
                    }

            # 5. Stitch final context
            context_text = self.stitcher.stitch(
                allocated_blocks,
                query,
                self.config.ordering,
                preserve_order=ranking_surface_lock_enabled,
            )

            # 6. Compute used tokens
            used_tokens = sum(ab.allocated_tokens for ab in allocated_blocks)

            # 7. Build provenance
            scored_map = {sb.block.block_id: sb for sb in scored_blocks}
            allocated_id_set = set(allocated_ids)
            drop_trace = []
            filtered_out_ids = set()
            low_value_suppressed_ids = set(
                low_value_suppression_trace.get("suppressed_block_ids", []) or []
            )
            if precision_filter_trace and precision_filter_trace.get("dropped_block_ids"):
                filtered_out_ids = set(precision_filter_trace["dropped_block_ids"])
            for block in blocks:
                scored = scored_map.get(block.block_id)
                reason = "kept"
                if block.block_id not in unique_ids:
                    reason = "dedup"
                elif block.block_id not in allocated_id_set:
                    reason = "budget"
                if block.block_id in filtered_out_ids:
                    reason = "precision_filter"
                if block.block_id in low_value_suppressed_ids:
                    reason = "low_value_suppression"
                drop_trace.append(
                    {
                        "block_id": block.block_id,
                        "file": block.file,
                        "start_line": block.start_line,
                        "end_line": block.end_line,
                        "symbol_id": block.symbol_id,
                        "estimated_tokens": self._estimate_tokens_with_tokenizer(block.content),
                        "semantic_score": scored.semantic_score if scored else None,
                        "name_score": scored.name_score if scored else None,
                        "structural_priority": scored.structural_priority if scored else None,
                        "novelty_score": scored.novelty_score if scored else None,
                        "coherence_score": scored.coherence_score if scored else None,
                        "final_score": scored.final_score if scored else None,
                        "drop_reason": reason,
                        "block_content": block.content if reason == "kept" else None,
                    }
                )
            kept_drop_entries = [d for d in drop_trace if d["drop_reason"] == "kept"]
            kept_file_counts = Counter(d["file"] for d in kept_drop_entries if d.get("file"))
            top_file_concentration = (
                max(kept_file_counts.values()) / max(1, len(kept_drop_entries))
                if kept_file_counts
                else 0.0
            )
            top3_ranked_survivors = sum(
                1 for d in drop_trace[:3] if d["drop_reason"] == "kept"
            )
            depth_preservation_check = {
                "top_file_concentration_ratio": round(top_file_concentration, 6),
                "top3_ranked_survivors": int(top3_ranked_survivors),
                "top3_ranked_retention_ratio": round(top3_ranked_survivors / 3.0, 6),
                "top3_min2_guard_passed": bool(top3_ranked_survivors >= 2),
                "multi_block_same_file_present": any(v >= 2 for v in kept_file_counts.values()),
                "file_repetition_distribution": dict(
                    sorted(kept_file_counts.items(), key=lambda kv: (-kv[1], kv[0]))
                ),
            }
            if top3_ranked_survivors < 2:
                logger.warning(
                    "[DEPTH_PRESERVATION] top3 survivor guard failed: survivors=%d query_id=%s",
                    top3_ranked_survivors,
                    query_id,
                )

            # Coherence refinement telemetry
            coherence_details = getattr(self.scorer, "_last_coherence_details", None) or []
            coherence_telemetry = {
                "enabled": getattr(self.config, "coherence_enabled", False),
                "blocks_refined": len(coherence_details),
                "mid_range_reorders": sum(
                    1 for a, b in zip(pre_coherence_ids[protect_n:], post_coherence_ids[protect_n:])
                    if a != b
                ) if len(pre_coherence_ids) > protect_n else 0,
            }
            if coherence_details:
                coherence_telemetry["max_coherence"] = max(d["capped"] for d in coherence_details)
                coherence_telemetry["mean_coherence"] = round(
                    sum(d["capped"] for d in coherence_details) / len(coherence_details), 4
                )
                coherence_telemetry["same_file_hits"] = sum(
                    1 for d in coherence_details if d["same_file_bonus"] > 0
                )
                coherence_telemetry["call_chain_hits"] = sum(
                    1 for d in coherence_details if d["call_chain_bonus"] > 0
                )

            # Stitch telemetry
            stitch_telemetry = getattr(self.stitcher, "_last_stitch_telemetry", None)

            provenance = {
                "query": query,
                "query_text": query,
                "unresolved_claim_hints": list(unresolved_claim_hints or []),
                "ranking_surface_lock_enabled": ranking_surface_lock_enabled,
                "ranking_order_preserved": ranking_order_preserved,
                "context_reorder_count": context_reorder_count,
                "ranking_authority_fallback": ranking_authority_fallback_trace,
                "stage_counts": stage_counts,
                "stage_file_histograms": stage_file_histograms,
                "scored_order_top10": scored_order_top10,
                "context_drop_trace": drop_trace,
                "coherence_refinement": coherence_telemetry,
                "stitching": stitch_telemetry,
                "submodular_packer": submodular_telemetry,
                "dynamic_budget": dynamic_budget_trace,
                "precision_filter": precision_filter_trace,
                "sparse_backfill": sparse_backfill_trace,
                "low_value_suppression": low_value_suppression_trace,
                "budget_guard": budget_guard_trace,
                "claim_gain_swap": claim_gain_swap_trace,
                "unresolved_evidence_injection": unresolved_evidence_injection_trace,
                "depth_preservation_check": depth_preservation_check,
                        "utilization_diagnostic": (
                            utilization_diagnostic_override
                            if utilization_diagnostic_override is not None
                            else getattr(self.budget_manager, "_last_utilization_diagnostic", None)
                        ),
                "context_synthesis": {
                    "synthesis_score": synthesis_profile.synthesis_score,
                    "concept_density": synthesis_profile.concept_density,
                    "file_dispersion": synthesis_profile.file_dispersion,
                    "semantic_entropy": synthesis_profile.semantic_entropy,
                    "retrieval_disagreement": synthesis_profile.retrieval_disagreement,
                },
                "context_integration": {
                    "integration_pressure": integration_profile.integration_pressure,
                    "file_dispersion": integration_profile.file_dispersion,
                    "coverage_slope": integration_profile.coverage_slope,
                    "redundancy_level": integration_profile.redundancy_level,
                    "semantic_entropy": integration_profile.semantic_entropy,
                },
                "blocks": [
                    {
                        "block_id": ab.block.block_id,
                        "file": ab.block.file,
                        "start_line": ab.block.start_line,
                        "end_line": ab.block.end_line,
                        "tokens": ab.allocated_tokens,
                        "provenance": list(ab.block.provenance),
                    }
                    for ab in allocated_blocks
                ]
            }

            # 8. Build explain trace
            tokens_remaining_for_generation = context_max_tokens_effective - used_tokens
            explain_trace = tuple(
                [
                    f"Selected {len(allocated_blocks)} blocks",
                    f"Context budget: {effective_context_budget}/{context_max_tokens_effective} tokens (reserve={self.config.generation_reserve_tokens})",
                    f"Used {used_tokens} context tokens, {tokens_remaining_for_generation} remaining for generation",
                    f"Stages: ranked={stage_counts['ranked_candidates']} assembled={stage_counts['assembled_blocks']} scored={stage_counts['scored_blocks']} dedup={stage_counts['dedup_blocks']} allocated={stage_counts['allocated_blocks']}",
                    f"Ranking surface lock={ranking_surface_lock_enabled} preserved={ranking_order_preserved} reorders={context_reorder_count}",
                ]
            )

            return ContextArtifact(
                query_id=query_id,
                context_text=context_text,
                blocks=tuple(ab.block for ab in allocated_blocks),
                token_budget=effective_context_budget,  # Effective budget after reserve
                used_tokens=used_tokens,
                provenance=provenance,
                explain_trace=explain_trace,
            )

        except Exception as e:
            import traceback, sys; sys.stderr.write(f"[CTX_ASSEMBLY_ERROR] {e}\n"); traceback.print_exc(file=sys.stderr); sys.stderr.flush()
            logger.error(f"Context assembly failed: {e}")
            # Return empty context on error
            return ContextArtifact(
                query_id=query_id,
                context_text="",
                blocks=tuple(),
                token_budget=self.config.max_tokens,
                used_tokens=0,
                provenance={"query": query, "query_text": query},
                explain_trace=tuple([f"Error: {str(e)}"]),
            )

    def _fallback_rank_locked_allocation(
        self,
        ranked_scored_blocks: list[ScoredBlock],
        effective_context_budget: int,
        query: str,
    ):
        """Budget-fit blocks in strict ranking order as a safe fallback."""
        budget_config = BudgetConfig(
            max_tokens=effective_context_budget,
            budget_mode=self.config.budget_mode,
            structural_priority_multiplier=self.config.structural_priority_multiplier,
        )
        return self.budget_manager.allocate(
            ranked_scored_blocks,
            {"query": query},
            budget_config,
            self.tokenizer,
            preserve_order=True,
        )

    @staticmethod
    def _compute_tail_density_ratio(
        density_curve: list[float] | None,
        epsilon: float | None = None,
        head_k: int = 3,
        tail_k: int = 3,
    ) -> float:
        if not density_curve or len(density_curve) < (head_k + tail_k):
            return 0.0
        tail = density_curve[-tail_k:]
        tail_avg = sum(float(v) for v in tail) / float(tail_k)
        if epsilon and epsilon > 0:
            return tail_avg / float(epsilon)
        head = density_curve[:head_k]
        head_avg = sum(float(v) for v in head) / float(head_k)
        if head_avg <= 0:
            return 0.0
        return tail_avg / head_avg

    def _dynamic_budget_decision(
        self,
        telemetry: dict,
        current_budget: int,
        trigger_used_pct: float,
        budget_limit_threshold: int,
        tail_density_ratio_trigger: float,
    ) -> dict:
        used_tokens = int(telemetry.get("total_tokens_used", 0) or 0)
        utilization = float(telemetry.get("token_utilization", 0.0) or 0.0)
        remaining_tokens = max(0, int(current_budget) - used_tokens)
        stop_reason = str(telemetry.get("stop_reason", "")) if telemetry else ""
        density_curve = telemetry.get("marginal_density_curve") if telemetry else None
        epsilon = telemetry.get("min_density_epsilon") if telemetry else None
        tail_density_ratio = self._compute_tail_density_ratio(
            density_curve if isinstance(density_curve, list) else None,
            epsilon=epsilon if isinstance(epsilon, (int, float)) else None,
        )

        decision = {
            "expand": False,
            "reason": "unknown",
            "used_tokens": used_tokens,
            "current_budget": int(current_budget),
            "remaining_tokens": remaining_tokens,
            "utilization": round(utilization, 6),
            "stop_reason": stop_reason,
            "tail_density_ratio": round(tail_density_ratio, 6),
        }

        if utilization < trigger_used_pct:
            decision["reason"] = "utilization_below_trigger"
            return decision
        limit_threshold = max(
            budget_limit_threshold,
            int(round(float(current_budget) * max(0.0, 1.0 - trigger_used_pct))),
        )
        if remaining_tokens > limit_threshold:
            decision["reason"] = "budget_not_limited"
            return decision
        if tail_density_ratio < tail_density_ratio_trigger:
            decision["reason"] = "tail_density_below_trigger"
            return decision

        decision["expand"] = True
        decision["reason"] = "tail_density_high"
        return decision

    def _estimate_tokens_with_tokenizer(self, content: str | None) -> int:
        """Estimate tokens using tokenizer if available; fallback to len//4."""
        text = content or ""
        if self.tokenizer is not None:
            try:
                return max(1, len(self.tokenizer.encode(text)))
            except Exception:
                pass
        return self.budget_manager._estimate_tokens(text)

    def _build_rank_locked_scored_blocks(
        self,
        blocks,
        debug_trace_map: dict[str, DebugTrace],
    ) -> list[ScoredBlock]:
        scored: list[ScoredBlock] = []
        for block in blocks:
            trace = debug_trace_map.get(block.block_id)
            semantic_score = float(trace.rerank_score) if trace else 0.0
            name_score = (
                float(trace.features.name_match_score)
                if trace and trace.features
                else 0.0
            )
            structural_priority = float(trace.struct_bonus) if trace else 0.0
            final_score = float(trace.final_score) if trace else 0.0
            scored.append(
                ScoredBlock(
                    block=block,
                    semantic_score=semantic_score,
                    name_score=name_score,
                    structural_priority=structural_priority,
                    novelty_score=0.0,
                    coherence_score=0.0,
                    final_score=final_score,
                )
            )
        return scored

    def _apply_precision_filter(
        self,
        allocated_blocks,
        scored_map: dict[str, ScoredBlock],
        query: str,
    ):
        """Conservative filter for low-signal spillover on identifier-rich queries."""
        if not allocated_blocks:
            return allocated_blocks, {"active": False, "reason": "no_allocated_blocks"}

        identifiers = self._extract_query_identifiers(query)
        min_identifiers = int(
            getattr(self.config, "precision_filter_query_identifier_min", 1) or 1
        )
        if len(identifiers) < min_identifiers:
            return allocated_blocks, {
                "active": False,
                "reason": "insufficient_query_identifiers",
                "query_identifiers": sorted(identifiers),
            }

        low_score_threshold = float(
            getattr(self.config, "precision_filter_low_score_threshold", 0.25) or 0.25
        )
        min_kept = int(getattr(self.config, "precision_filter_min_kept_blocks", 10) or 10)

        anchor_files: set[str] = set()
        for ab in allocated_blocks:
            if self._block_identifier_overlap(ab.block, identifiers) and ab.block.file:
                anchor_files.add(ab.block.file)

        if not anchor_files:
            return allocated_blocks, {
                "active": False,
                "reason": "no_anchor_files",
                "query_identifiers": sorted(identifiers),
            }

        kept = []
        dropped_ids = []
        for ab in allocated_blocks:
            sb = scored_map.get(ab.block.block_id)
            final_score = float(sb.final_score) if sb else 0.0
            file_is_anchor = ab.block.file in anchor_files
            has_identifier_overlap = self._block_identifier_overlap(ab.block, identifiers)

            drop = (
                (not file_is_anchor)
                and (not has_identifier_overlap)
                and final_score < low_score_threshold
            )
            if drop:
                dropped_ids.append(ab.block.block_id)
            else:
                kept.append(ab)

        if len(kept) < min_kept:
            return allocated_blocks, {
                "active": False,
                "reason": "min_kept_guard",
                "query_identifiers": sorted(identifiers),
                "anchor_files": sorted(anchor_files),
                "attempted_drop_count": len(dropped_ids),
                "kept_after_filter": len(kept),
            }

        return kept, {
            "active": True,
            "reason": "applied",
            "query_identifiers": sorted(identifiers),
            "anchor_files": sorted(anchor_files),
            "low_score_threshold": low_score_threshold,
            "dropped_count": len(dropped_ids),
            "dropped_block_ids": dropped_ids,
            "kept_count": len(kept),
        }

    @staticmethod
    def _extract_query_identifiers(query: str) -> set[str]:
        query = query or ""
        identifiers: set[str] = set()
        pattern = r"\b[A-Z][a-zA-Z0-9]+\b|\b[a-z]+_[a-z0-9_]+\b|\b[A-Z][A-Z0-9_]{2,}\b"
        for match in re.findall(pattern, query):
            token = match.strip().lower()
            if len(token) >= 4:
                identifiers.add(token)
        return identifiers

    @staticmethod
    def _block_identifier_overlap(block, identifiers: set[str]) -> bool:
        if not identifiers:
            return False
        hay_raw = f"{(block.file or '').lower()} {(block.symbol_name or '').lower()}"
        hay = re.sub(r"[^a-z0-9]+", "", hay_raw)
        for tok in identifiers:
            norm_tok = re.sub(r"[^a-z0-9]+", "", tok.lower())
            if norm_tok and norm_tok in hay:
                return True
        return False

    def _apply_sparse_backfill(
        self,
        allocated_blocks,
        ranked_scored_blocks: list[ScoredBlock],
        effective_context_budget: int,
    ):
        """Append next-ranked unseen blocks when context is under-filled."""
        if not allocated_blocks:
            return allocated_blocks, {"active": False, "reason": "no_allocated_blocks"}

        current_tokens = sum(int(ab.allocated_tokens) for ab in allocated_blocks)
        current_blocks = len(allocated_blocks)
        utilization = (current_tokens / max(1, effective_context_budget))

        min_util = float(getattr(self.config, "sparse_backfill_min_utilization", 0.45) or 0.45)
        min_blocks = int(getattr(self.config, "sparse_backfill_min_blocks", 18) or 18)
        max_add = int(
            getattr(self.config, "sparse_backfill_max_additional_blocks", 10) or 10
        )
        needs_backfill = (utilization < min_util) or (current_blocks < min_blocks)
        if not needs_backfill:
            return allocated_blocks, {
                "active": False,
                "reason": "not_sparse",
                "utilization": round(utilization, 6),
                "blocks": current_blocks,
            }

        selected_ids = {ab.block.block_id for ab in allocated_blocks}
        target_tokens = int(min_util * effective_context_budget)
        candidates = [sb for sb in ranked_scored_blocks if sb.block.block_id not in selected_ids]

        added = []
        added_ids = []
        for sb in candidates:
            if len(added) >= max_add:
                break
            est_tokens = self._estimate_tokens_with_tokenizer(sb.block.content)
            if current_tokens + est_tokens > effective_context_budget:
                continue
            from homllm.context.interfaces import AllocatedBlock
            added_block = AllocatedBlock(
                block=sb.block,
                allocated_tokens=est_tokens,
                truncated_content=sb.block.content or "",
            )
            added.append(added_block)
            added_ids.append(sb.block.block_id)
            current_tokens += est_tokens
            if current_tokens >= target_tokens and (current_blocks + len(added)) >= min_blocks:
                break

        if not added:
            return allocated_blocks, {
                "active": False,
                "reason": "no_eligible_backfill",
                "utilization_before": round(utilization, 6),
                "blocks_before": current_blocks,
                "target_tokens": target_tokens,
            }

        merged = list(allocated_blocks) + added
        return merged, {
            "active": True,
            "reason": "applied",
            "utilization_before": round(utilization, 6),
            "blocks_before": current_blocks,
            "target_tokens": target_tokens,
            "added_count": len(added),
            "added_block_ids": added_ids,
            "tokens_after": current_tokens,
            "blocks_after": len(merged),
        }

    def _apply_low_value_suppression(self, allocated_blocks):
        """Drop obvious low-value glue blocks without violating min-keep."""
        if not allocated_blocks:
            return allocated_blocks, {"active": False, "reason": "no_allocated_blocks"}

        min_keep = int(getattr(self.config, "low_value_suppression_min_keep_blocks", 10) or 10)
        eligible_ids = {
            ab.block.block_id
            for ab in allocated_blocks
            if self._is_low_value_glue_block(ab.block)
        }
        if not eligible_ids:
            return allocated_blocks, {
                "active": False,
                "reason": "no_eligible_low_value_blocks",
                "suppressed_block_ids": [],
                "blocks_suppressed": 0,
            }

        kept = [ab for ab in allocated_blocks if ab.block.block_id not in eligible_ids]
        if len(kept) < min_keep:
            return allocated_blocks, {
                "active": False,
                "reason": "min_keep_guard",
                "suppressed_block_ids": [],
                "blocks_suppressed": 0,
                "candidate_block_ids": sorted(eligible_ids),
            }

        return kept, {
            "active": True,
            "reason": "applied",
            "suppressed_block_ids": sorted(eligible_ids),
            "blocks_suppressed": len(eligible_ids),
            "blocks_before": len(allocated_blocks),
            "blocks_after": len(kept),
        }

    @staticmethod
    def _is_low_value_glue_block(block) -> bool:
        file_path = str(getattr(block, "file", "") or "").replace("\\", "/")
        if not file_path.endswith("__init__.py"):
            return False

        content = str(getattr(block, "content", "") or "").strip()
        if not content:
            return True

        meaningful_lines = [
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not meaningful_lines:
            return True

        allowed_prefixes = ("from ", "import ", "__all__")
        for line in meaningful_lines:
            if line.startswith(('"""', "'''")) or line.endswith(('"""', "'''")):
                continue
            if line.startswith(allowed_prefixes):
                continue
            return False
        return True

    def _apply_claim_gain_epsilon_swap(
        self,
        allocated_blocks,
        ranked_scored_blocks: list[ScoredBlock],
        effective_context_budget: int,
        unresolved_claim_hints: list[str],
    ):
        """Swap near-threshold selected blocks with higher claim-gain candidates."""
        if not allocated_blocks:
            return allocated_blocks, {"active": False, "reason": "no_allocated_blocks"}
        if not unresolved_claim_hints:
            return allocated_blocks, {"active": False, "reason": "no_unresolved_claim_hints"}

        epsilon = float(getattr(self.config, "claim_gain_swap_score_epsilon", 0.02) or 0.02)
        max_swaps = int(getattr(self.config, "claim_gain_swap_max_swaps", 2) or 2)
        min_relevance_floor = float(
            getattr(self.config, "claim_gain_swap_min_relevance_floor", 0.25) or 0.25
        )
        if max_swaps <= 0:
            return allocated_blocks, {"active": False, "reason": "max_swaps_disabled"}

        hint_terms = self._extract_hint_terms(unresolved_claim_hints)
        if not hint_terms:
            return allocated_blocks, {
                "active": False,
                "reason": "no_hint_terms",
                "unresolved_claim_hints": list(unresolved_claim_hints),
            }

        scored_map = {sb.block.block_id: sb for sb in ranked_scored_blocks}
        selected_ids = {ab.block.block_id for ab in allocated_blocks}
        selected_list = [ab.block.block_id for ab in allocated_blocks]
        excluded = [sb for sb in ranked_scored_blocks if sb.block.block_id not in selected_ids]
        if not excluded:
            return allocated_blocks, {"active": False, "reason": "no_excluded_candidates"}

        tokens_used = sum(int(ab.allocated_tokens) for ab in allocated_blocks)
        # Prefer swaps against lowest-ranked selected blocks first.
        selected_list_reversed = list(reversed(selected_list))
        swaps = []

        def _score_of(block_id: str) -> float:
            sb = scored_map.get(block_id)
            return float(sb.final_score) if sb else 0.0

        def _claim_gain(sb: ScoredBlock) -> float:
            return self._compute_claim_gain(sb.block, hint_terms)

        for selected_id in selected_list_reversed:
            if len(swaps) >= max_swaps:
                break
            selected_sb = scored_map.get(selected_id)
            if not selected_sb:
                continue
            selected_score = float(selected_sb.final_score)
            selected_gain = _claim_gain(selected_sb)
            selected_tokens = self._estimate_tokens_with_tokenizer(selected_sb.block.content)

            best = None
            for ex in excluded:
                ex_id = ex.block.block_id
                if ex_id in selected_ids:
                    continue
                ex_score = float(ex.final_score)
                if ex_score < min_relevance_floor:
                    continue
                if abs(ex_score - selected_score) > epsilon:
                    continue
                ex_gain = _claim_gain(ex)
                if ex_gain <= selected_gain:
                    continue
                ex_tokens = self._estimate_tokens_with_tokenizer(ex.block.content)
                new_tokens = tokens_used - selected_tokens + ex_tokens
                if new_tokens > effective_context_budget:
                    continue
                cand = (ex, ex_gain, ex_score, ex_tokens, new_tokens)
                if best is None or ex_gain > best[1] or (ex_gain == best[1] and ex_score > best[2]):
                    best = cand

            if best is None:
                continue

            ex, ex_gain, ex_score, ex_tokens, new_tokens = best
            selected_ids.remove(selected_id)
            selected_ids.add(ex.block.block_id)
            tokens_used = new_tokens
            swaps.append(
                {
                    "out_block_id": selected_id,
                    "in_block_id": ex.block.block_id,
                    "out_score": selected_score,
                    "in_score": ex_score,
                    "score_delta": ex_score - selected_score,
                    "out_claim_gain": selected_gain,
                    "in_claim_gain": ex_gain,
                    "claim_gain_delta": ex_gain - selected_gain,
                    "out_tokens": selected_tokens,
                    "in_tokens": ex_tokens,
                }
            )

        if not swaps:
            return allocated_blocks, {
                "active": False,
                "reason": "no_eligible_swap",
                "epsilon": epsilon,
                "max_swaps": max_swaps,
                "min_relevance_floor": min_relevance_floor,
                "hint_term_count": len(hint_terms),
            }

        # Preserve ranked order while applying swapped selected-id set.
        from homllm.context.interfaces import AllocatedBlock

        merged = []
        for sb in ranked_scored_blocks:
            bid = sb.block.block_id
            if bid not in selected_ids:
                continue
            est_tokens = self._estimate_tokens_with_tokenizer(sb.block.content)
            merged.append(
                AllocatedBlock(
                    block=sb.block,
                    allocated_tokens=est_tokens,
                    truncated_content=sb.block.content or "",
                )
            )

        return merged, {
            "active": True,
            "reason": "applied",
            "epsilon": epsilon,
            "max_swaps": max_swaps,
            "min_relevance_floor": min_relevance_floor,
            "hint_term_count": len(hint_terms),
            "swaps_applied": len(swaps),
            "swaps": swaps,
        }

    def _apply_unresolved_evidence_injection(
        self,
        allocated_blocks,
        ranked_scored_blocks: list[ScoredBlock],
        effective_context_budget: int,
        unresolved_claim_hints: list[str],
        query: str,
    ):
        """Force small amounts of unresolved-claim evidence into final context."""
        del query  # Reserved for future telemetry/detail without affecting determinism.

        if not getattr(self.config, "unresolved_evidence_injection_enabled", False):
            return allocated_blocks, {"active": False, "reason": "disabled"}
        if not allocated_blocks:
            return allocated_blocks, {"active": False, "reason": "no_allocated_blocks"}
        if not unresolved_claim_hints:
            return allocated_blocks, {"active": False, "reason": "no_unresolved_claim_hints"}

        hint_terms = self._extract_hint_terms(unresolved_claim_hints)
        if not hint_terms:
            return allocated_blocks, {
                "active": False,
                "reason": "no_hint_terms",
                "candidate_count_considered": 0,
                "blocks_injected": 0,
                "replaced_block_ids": [],
                "injected_block_ids": [],
                "tokens_before": sum(int(ab.allocated_tokens) for ab in allocated_blocks),
                "tokens_after": sum(int(ab.allocated_tokens) for ab in allocated_blocks),
                "claim_gain_delta_total": 0.0,
            }

        scored_map = {sb.block.block_id: sb for sb in ranked_scored_blocks}
        selected_ids = {ab.block.block_id for ab in allocated_blocks}
        excluded = [sb for sb in ranked_scored_blocks if sb.block.block_id not in selected_ids]
        tokens_before = sum(int(ab.allocated_tokens) for ab in allocated_blocks)

        if not excluded:
            return allocated_blocks, {
                "active": False,
                "reason": "no_excluded_candidates",
                "candidate_count_considered": 0,
                "blocks_injected": 0,
                "replaced_block_ids": [],
                "injected_block_ids": [],
                "tokens_before": tokens_before,
                "tokens_after": tokens_before,
                "claim_gain_delta_total": 0.0,
            }

        min_relevance_floor = float(
            getattr(self.config, "unresolved_evidence_injection_relevance_floor", 0.15)
            or 0.15
        )
        min_claim_gain = float(
            getattr(self.config, "unresolved_evidence_injection_min_claim_gain", 0.1) or 0.1
        )
        max_blocks = int(
            getattr(self.config, "unresolved_evidence_injection_max_blocks", 2) or 2
        )
        max_token_share = float(
            getattr(self.config, "unresolved_evidence_injection_max_token_share", 0.15) or 0.15
        )
        replace_from_tail = bool(
            getattr(self.config, "unresolved_evidence_injection_replace_from_tail", True)
        )
        if max_blocks <= 0:
            return allocated_blocks, {
                "active": False,
                "reason": "disabled",
                "candidate_count_considered": 0,
                "blocks_injected": 0,
                "replaced_block_ids": [],
                "injected_block_ids": [],
                "tokens_before": tokens_before,
                "tokens_after": tokens_before,
                "claim_gain_delta_total": 0.0,
            }

        eligible_candidates = []
        for sb in excluded:
            final_score = float(sb.final_score)
            if final_score < min_relevance_floor:
                continue
            claim_gain = self._compute_claim_gain(sb.block, hint_terms)
            if claim_gain < min_claim_gain:
                continue
            est_tokens = self._estimate_tokens_with_tokenizer(sb.block.content)
            eligible_candidates.append((sb, claim_gain, final_score, est_tokens))

        if not eligible_candidates:
            return allocated_blocks, {
                "active": False,
                "reason": "no_eligible_candidates",
                "candidate_count_considered": 0,
                "blocks_injected": 0,
                "replaced_block_ids": [],
                "injected_block_ids": [],
                "tokens_before": tokens_before,
                "tokens_after": tokens_before,
                "claim_gain_delta_total": 0.0,
            }

        eligible_candidates.sort(key=lambda item: (-item[1], -item[2], item[3], item[0].block.block_id))

        token_cap = max(1, int(effective_context_budget * max_token_share))
        current_tokens = tokens_before
        injected_token_total = 0
        injected_ids: list[str] = []
        replaced_ids: list[str] = []
        claim_gain_delta_total = 0.0

        selected_order = [ab.block.block_id for ab in allocated_blocks]
        if replace_from_tail:
            selected_candidates = list(reversed(selected_order))
        else:
            selected_candidates = list(selected_order)

        for ex, ex_gain, _ex_score, ex_tokens in eligible_candidates:
            if len(injected_ids) >= max_blocks:
                break
            if ex.block.block_id in selected_ids:
                continue
            if injected_token_total + ex_tokens > token_cap:
                continue

            replacement_found = False
            for selected_id in selected_candidates:
                if selected_id not in selected_ids:
                    continue
                selected_sb = scored_map.get(selected_id)
                if not selected_sb:
                    continue
                if self._block_is_protected(selected_sb.block):
                    continue
                selected_gain = self._compute_claim_gain(selected_sb.block, hint_terms)
                selected_tokens = self._estimate_tokens_with_tokenizer(selected_sb.block.content)
                new_tokens = current_tokens - selected_tokens + ex_tokens
                if new_tokens > effective_context_budget:
                    continue

                selected_ids.remove(selected_id)
                selected_ids.add(ex.block.block_id)
                current_tokens = new_tokens
                injected_token_total += ex_tokens
                injected_ids.append(ex.block.block_id)
                replaced_ids.append(selected_id)
                claim_gain_delta_total += max(0.0, ex_gain - selected_gain)
                replacement_found = True
                break

            if not replacement_found:
                continue

        if not injected_ids:
            return allocated_blocks, {
                "active": False,
                "reason": "no_budget_safe_replacement",
                "candidate_count_considered": len(eligible_candidates),
                "blocks_injected": 0,
                "replaced_block_ids": [],
                "injected_block_ids": [],
                "tokens_before": tokens_before,
                "tokens_after": tokens_before,
                "claim_gain_delta_total": 0.0,
            }

        from homllm.context.interfaces import AllocatedBlock

        merged = []
        for sb in ranked_scored_blocks:
            bid = sb.block.block_id
            if bid not in selected_ids:
                continue
            est_tokens = self._estimate_tokens_with_tokenizer(sb.block.content)
            merged.append(
                AllocatedBlock(
                    block=sb.block,
                    allocated_tokens=est_tokens,
                    truncated_content=sb.block.content or "",
                )
            )

        return merged, {
            "active": True,
            "reason": "applied",
            "candidate_count_considered": len(eligible_candidates),
            "blocks_injected": len(injected_ids),
            "replaced_block_ids": replaced_ids,
            "injected_block_ids": injected_ids,
            "tokens_before": tokens_before,
            "tokens_after": sum(int(ab.allocated_tokens) for ab in merged),
            "claim_gain_delta_total": round(claim_gain_delta_total, 6),
        }

    def _apply_final_budget_guard(self, allocated_blocks, effective_context_budget: int) -> dict:
        """Trim lowest-ranked tail blocks if post-selection stages exceed the effective budget."""
        current_tokens = sum(int(ab.allocated_tokens) for ab in allocated_blocks)
        if current_tokens <= effective_context_budget:
            return {
                "active": False,
                "reason": "within_budget",
                "tokens_before": current_tokens,
                "tokens_after": current_tokens,
                "removed_block_ids": [],
                "blocks_removed": 0,
            }

        removed_block_ids: list[str] = []
        trimmed_tokens = current_tokens
        for ab in reversed(allocated_blocks):
            if trimmed_tokens <= effective_context_budget:
                break
            trimmed_tokens -= int(ab.allocated_tokens)
            removed_block_ids.append(ab.block.block_id)

        if trimmed_tokens > effective_context_budget:
            return {
                "active": False,
                "reason": "unable_to_trim",
                "tokens_before": current_tokens,
                "tokens_after": current_tokens,
                "removed_block_ids": [],
                "blocks_removed": 0,
            }

        return {
            "active": True,
            "reason": "trimmed_to_budget",
            "tokens_before": current_tokens,
            "tokens_after": trimmed_tokens,
            "removed_block_ids": removed_block_ids,
            "blocks_removed": len(removed_block_ids),
        }

    @staticmethod
    def _block_is_protected(block) -> bool:
        provenance = {str(p).upper() for p in tuple(getattr(block, "provenance", ()) or ())}
        return bool(provenance.intersection({"PROTECT", "PRESERVE", "KEEP", "ANCHOR"}))

    @staticmethod
    def _extract_hint_terms(unresolved_claim_hints: list[str]) -> set[str]:
        """Extract normalized terms from unresolved claim hints."""
        stop_words = {
            "the", "and", "for", "with", "from", "that", "this", "when", "how",
            "does", "into", "across", "between", "using", "about", "query",
            "claim", "required", "context", "code", "method", "class",
        }
        terms: set[str] = set()
        for hint in unresolved_claim_hints:
            for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]+", str(hint or "").lower()):
                if len(tok) < 3:
                    continue
                if tok in stop_words:
                    continue
                terms.add(tok)
        return terms

    @staticmethod
    def _compute_claim_gain(block, hint_terms: set[str]) -> float:
        """Compute lightweight claim gain from hint-term overlap."""
        if not hint_terms:
            return 0.0
        file_sym_hay = " ".join(
            [
                str(getattr(block, "file", "") or ""),
                str(getattr(block, "symbol_name", "") or ""),
                str(getattr(block, "symbol_id", "") or ""),
            ]
        ).lower()
        content_hay = str(getattr(block, "content", "") or "")[:1600].lower()
        file_sym_hits = 0
        content_hits = 0
        for term in hint_terms:
            if term in file_sym_hay:
                file_sym_hits += 1
            elif term in content_hay:
                content_hits += 1
        # Prioritize file/symbol alignment over broad content overlap.
        weighted_hits = (2.0 * file_sym_hits) + (0.5 * content_hits)
        return min(1.0, weighted_hits / float(max(1, len(hint_terms))))

    @staticmethod
    def _count_reorders(source_ids: list[str], target_ids: list[str]) -> int:
        if len(source_ids) <= 1 or len(target_ids) <= 1:
            return 0
        first_index: dict[str, int] = {}
        for idx, doc_id in enumerate(source_ids):
            if doc_id not in first_index:
                first_index[doc_id] = idx
        mapped = [first_index[doc_id] for doc_id in target_ids if doc_id in first_index]
        if len(mapped) <= 1:
            return 0
        reorder_count = 0
        previous = mapped[0]
        for current in mapped[1:]:
            if current < previous:
                reorder_count += 1
            previous = current
        return reorder_count
