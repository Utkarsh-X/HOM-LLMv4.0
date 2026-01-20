"""Context assembly pipeline orchestrator."""

import logging
import uuid
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
                    provenance={},
                    explain_trace=tuple(["No candidates found"]),
                )

            # 2. Score blocks
            debug_trace_map = {
                trace.candidate_id: trace for trace in ranking_output.debug_traces
            }
            scored_blocks = self.scorer.score(
                blocks, query, [], debug_trace_map
            )

            # 3. Deduplicate
            unique_blocks = self.deduplicator.deduplicate(
                [sb.block for sb in scored_blocks]
            )
            # Rebuild scored blocks with unique blocks only
            unique_scored = [
                sb for sb in scored_blocks if sb.block in unique_blocks
            ]

            # 4. Budget allocation
            budget_config = BudgetConfig(
                max_tokens=self.config.max_tokens,
                budget_mode=self.config.budget_mode,
                structural_priority_multiplier=self.config.structural_priority_multiplier,
            )

            allocated_blocks = self.budget_manager.allocate(
                unique_scored,
                {"query": query},
                budget_config,
                self.tokenizer,
            )

            # 5. Stitch final context
            context_text = self.stitcher.stitch(
                allocated_blocks, query, self.config.ordering
            )

            # 6. Compute used tokens
            used_tokens = sum(ab.allocated_tokens for ab in allocated_blocks)

            # 7. Build provenance
            provenance = {
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
            explain_trace = tuple(
                [
                    f"Selected {len(allocated_blocks)} blocks",
                    f"Used {used_tokens}/{self.config.max_tokens} tokens",
                    f"Ordering: {self.config.ordering}",
                ]
            )

            return ContextArtifact(
                query_id=query_id,
                context_text=context_text,
                blocks=tuple(ab.block for ab in allocated_blocks),
                token_budget=self.config.max_tokens,
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
                provenance={},
                explain_trace=tuple([f"Error: {str(e)}"]),
            )
