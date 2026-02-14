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
)
from homllm.context.scorer import ContextBlockScorer
from homllm.context.stitcher import ContextStitcher
from homllm.ranking.interfaces import RankingOutput

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
    ):
        """
        Initialize context pipeline.
        
        Args:
            config: Context configuration
            embedder: Embedder for coherence scoring (optional)
            tokenizer: Tokenizer for exact token counting (optional)
        """
        self.config = config
        self.tokenizer = tokenizer

        self.assembler = BlockAssembler()
        self.scorer = ContextBlockScorer(embedder, config)
        self.deduplicator = ContextDeduplicator()
        self.budget_manager = TokenBudgetManager()
        self.stitcher = ContextStitcher()

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

            if not blocks:
                # Zero candidates - return empty context
                return ContextArtifact(
                    query_id=query_id,
                    context_text="",
                    blocks=tuple(),
                    token_budget=self.config.max_tokens,
                    used_tokens=0,
                    provenance={"query": query, "query_text": query},
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

            # 2. Score blocks
            scored_blocks = self.scorer.score(
                blocks, query, [], debug_trace_map
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
                for sb in sorted(scored_blocks, key=lambda x: x.final_score, reverse=True)[:10]
            ]

            # 3. Deduplicate
            unique_blocks = self.deduplicator.deduplicate(
                [sb.block for sb in scored_blocks]
            )
            stage_counts["dedup_blocks"] = len(unique_blocks)
            stage_file_histograms["dedup"] = _file_hist(unique_blocks)
            # Rebuild scored blocks with unique blocks only
            unique_scored = [
                sb for sb in scored_blocks if sb.block in unique_blocks
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

            # 5. Stitch final context
            context_text = self.stitcher.stitch(
                allocated_blocks, query, self.config.ordering
            )

            # 6. Compute used tokens
            used_tokens = sum(ab.allocated_tokens for ab in allocated_blocks)

            # 7. Build provenance
            scored_map = {sb.block.block_id: sb for sb in scored_blocks}
            unique_ids = {b.block_id for b in unique_blocks}
            allocated_ids = {ab.block.block_id for ab in allocated_blocks}
            drop_trace = []
            for block in blocks:
                scored = scored_map.get(block.block_id)
                reason = "kept"
                if block.block_id not in unique_ids:
                    reason = "dedup"
                elif block.block_id not in allocated_ids:
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
                    }
                )

            provenance = {
                "query": query,
                "query_text": query,
                "stage_counts": stage_counts,
                "stage_file_histograms": stage_file_histograms,
                "scored_order_top10": scored_order_top10,
                "context_drop_trace": drop_trace,
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
                    f"Ordering: {self.config.ordering}",
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
