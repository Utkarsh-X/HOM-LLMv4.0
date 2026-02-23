"""Context assembly pipeline orchestrator."""

import logging
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

            # 4. Budget allocation
            # Apply generation reserve: context cannot use the full token budget
            effective_context_budget = self.config.max_tokens - self.config.generation_reserve_tokens
            
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

            ranking_ids = [block.block_id for block in blocks]
            allocated_ids = [ab.block.block_id for ab in allocated_blocks]
            context_reorder_count = self._count_reorders(ranking_ids, allocated_ids)
            ranking_order_preserved = context_reorder_count == 0

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
                        raise RuntimeError(
                            "RANKING_AUTHORITY_LOCK_VIOLATION (top-N):"
                            f"top_{top_n}_reorder_count={top_reorders}"
                        )
                    # Log coherence-driven reorders (allowed)
                    logger.info(
                        "[CONTEXT] coherence mid-range reorders=%d (allowed, top-%d protected)",
                        context_reorder_count, top_n,
                    )
                else:
                    raise RuntimeError(
                        "RANKING_AUTHORITY_LOCK_VIOLATION:"
                        f"context_reorder_count={context_reorder_count}"
                    )

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
            for block in blocks:
                scored = scored_map.get(block.block_id)
                reason = "kept"
                if block.block_id not in unique_ids:
                    reason = "dedup"
                elif block.block_id not in allocated_id_set:
                    reason = "budget"
                drop_trace.append(
                    {
                        "block_id": block.block_id,
                        "file": block.file,
                        "start_line": block.start_line,
                        "end_line": block.end_line,
                        "symbol_id": block.symbol_id,
                        "estimated_tokens": self.budget_manager._estimate_tokens(block.content),
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
                "ranking_surface_lock_enabled": ranking_surface_lock_enabled,
                "ranking_order_preserved": ranking_order_preserved,
                "context_reorder_count": context_reorder_count,
                "stage_counts": stage_counts,
                "stage_file_histograms": stage_file_histograms,
                "scored_order_top10": scored_order_top10,
                "context_drop_trace": drop_trace,
                "coherence_refinement": coherence_telemetry,
                "stitching": stitch_telemetry,
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
            tokens_remaining_for_generation = self.config.max_tokens - used_tokens
            explain_trace = tuple(
                [
                    f"Selected {len(allocated_blocks)} blocks",
                    f"Context budget: {effective_context_budget}/{self.config.max_tokens} tokens (reserve={self.config.generation_reserve_tokens})",
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
            if "RANKING_AUTHORITY_LOCK_VIOLATION" in str(e):
                raise
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
