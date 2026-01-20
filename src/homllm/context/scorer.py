"""Block scorer implementation."""

import logging
from typing import Optional

from homllm.context.interfaces import (
    BlockScorer,
    ContextBlock,
    ContextConfig,
    ScoredBlock,
)
from homllm.ranking.interfaces import DebugTrace

logger = logging.getLogger(__name__)


class ContextBlockScorer(BlockScorer):
    """Scores context blocks for selection."""

    def __init__(self, embedder: Optional[object] = None, config: Optional[ContextConfig] = None):
        """
        Initialize block scorer.
        
        Args:
            embedder: Embedder for coherence scoring (optional)
            config: Context configuration (required for scoring)
        """
        self.embedder = embedder
        self.config = config

    def score(
        self,
        blocks: list[ContextBlock],
        query: str,
        selected_blocks: list[ContextBlock],
        debug_traces: dict[str, DebugTrace],
    ) -> list[ScoredBlock]:
        """
        Score blocks for context selection.
        
        Signals:
        - semantic_score: From reranker (from debug_traces)
        - name_score: Identifier overlap
        - structural_priority: Entrypoint/decorator weight
        - novelty_score: Difference from selected
        - coherence_score: Fit with current context
        """
        scored = []

        # Compute novelty scores (difference from selected blocks)
        selected_content = {b.content[:100] for b in selected_blocks}

        for block in blocks:
            # Get semantic score from debug trace
            trace = debug_traces.get(block.block_id)
            semantic_score = trace.final_score if trace else 0.0

            # Name score (identifier overlap with query)
            name_score = self._compute_name_score(block, query)

            # Structural priority (from provenance)
            structural_priority = self._compute_structural_priority(block)

            # Novelty score (difference from selected)
            novelty_score = self._compute_novelty_score(block, selected_content)

            # Coherence score (fit with current context)
            coherence_score = self._compute_coherence_score(
                block, selected_blocks, query
            )

            # Final score (weighted combination - all weights from config)
            if self.config:
                final_score = (
                    self.config.w_semantic * semantic_score
                    + self.config.w_name * name_score
                    + self.config.w_structural * structural_priority
                    + self.config.w_novelty * novelty_score
                    + self.config.w_coherence * coherence_score
                )
            else:
                # Fallback to defaults if config not provided
                final_score = (
                    0.4 * semantic_score
                    + 0.2 * name_score
                    + 0.2 * structural_priority
                    + 0.1 * novelty_score
                    + 0.1 * coherence_score
                )

            scored_block = ScoredBlock(
                block=block,
                semantic_score=semantic_score,
                name_score=name_score,
                structural_priority=structural_priority,
                novelty_score=novelty_score,
                coherence_score=coherence_score,
                final_score=final_score,
            )

            scored.append(scored_block)

        # Sort by final score descending
        scored.sort(key=lambda s: s.final_score, reverse=True)

        return scored

    def _compute_name_score(self, block: ContextBlock, query: str) -> float:
        """Compute identifier overlap score."""
        if not block.symbol_name:
            return 0.0

        query_terms = set(query.lower().split())
        symbol_terms = set(block.symbol_name.lower().split("_"))

        if not query_terms or not symbol_terms:
            return 0.0

        overlap = len(query_terms & symbol_terms)
        return overlap / max(len(query_terms), len(symbol_terms))

    def _compute_structural_priority(self, block: ContextBlock) -> float:
        """Compute structural priority from provenance."""
        priority = 0.0

        # Use config values if available, otherwise fallback to defaults
        decorator_bonus = self.config.structural_priority_decorator_bonus if self.config else 0.3
        callgraph_bonus = self.config.structural_priority_callgraph_bonus if self.config else 0.2
        entrypoint_bonus = self.config.structural_priority_entrypoint_bonus if self.config else 0.5
        cap = self.config.structural_priority_cap if self.config else 1.0

        if "expansion:decorator" in block.provenance:
            priority += decorator_bonus

        if "expansion:callee" in block.provenance:
            priority += callgraph_bonus

        # Check if entrypoint (main, run, etc.)
        if block.symbol_name:
            entrypoint_names = {"main", "run", "start", "entry", "init"}
            if block.symbol_name.lower() in entrypoint_names:
                priority += entrypoint_bonus

        return min(priority, cap)

    def _compute_novelty_score(
        self, block: ContextBlock, selected_content: set[str]
    ) -> float:
        """Compute novelty (difference from selected blocks)."""
        block_preview = block.content[:100]
        if block_preview in selected_content:
            return 0.0  # Not novel
        return 1.0  # Novel

    def _compute_coherence_score(
        self,
        block: ContextBlock,
        selected_blocks: list[ContextBlock],
        query: str,
    ) -> float:
        """Compute coherence (fit with current context)."""
        if not selected_blocks:
            return 1.0  # First block is always coherent

        # Use config values if available, otherwise fallback to defaults
        same_file_bonus = self.config.coherence_same_file_bonus if self.config else 0.8
        different_file_bonus = self.config.coherence_different_file_bonus if self.config else 0.5

        # Simple heuristic: check if block is from same file
        selected_files = {b.file for b in selected_blocks}
        if block.file in selected_files:
            return same_file_bonus

        return different_file_bonus
