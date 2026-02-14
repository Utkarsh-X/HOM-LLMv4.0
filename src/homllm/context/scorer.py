"""Block scorer implementation."""

import logging
from collections import Counter
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

    _FILE_DIVERSITY_BETA = 0.2

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
        scored: list[ScoredBlock] = []

        # Precompute raw semantic scores from ranking traces.
        semantic_raw: dict[str, float] = {}
        for block in blocks:
            trace = debug_traces.get(block.block_id)
            if trace:
                semantic_raw[block.block_id] = trace.base_score + trace.rerank_score
            else:
                semantic_raw[block.block_id] = 0.0

        raw_values = list(semantic_raw.values())
        raw_min = min(raw_values) if raw_values else 0.0
        raw_max = max(raw_values) if raw_values else 0.0
        raw_range = raw_max - raw_min

        for block in blocks:
            # Normalize semantic score to [0, 1] for stability
            raw_score = semantic_raw.get(block.block_id, 0.0)
            if raw_range > 0:
                semantic_score = (raw_score - raw_min) / raw_range
            else:
                semantic_score = 0.5 if raw_values else 0.0

            # Name score (identifier overlap with query)
            name_score = self._compute_name_score(block, query)

            structural_priority = 0.0
            novelty_score = 0.0
            coherence_score = 0.0

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

        # Context pipeline preserves order downstream (`preserve_order=True` in budget allocation).
        # So diversification must be represented as a deterministic ordering here, not as token caps.
        distinct_files = len({b.block.file for b in scored if b.block.file})
        if distinct_files <= 1:
            return scored

        remaining: list[tuple[int, ScoredBlock]] = list(enumerate(scored))
        selected: list[ScoredBlock] = []
        per_file: Counter[str] = Counter()

        while remaining:
            best_i = 0
            best_score = None
            for i, (orig_idx, sb) in enumerate(remaining):
                file_key = sb.block.file or ""
                decay = 1.0 / (1.0 + self._FILE_DIVERSITY_BETA * float(per_file.get(file_key, 0)))
                adjusted = sb.final_score * decay
                key = (adjusted, -orig_idx)
                if best_score is None or key > best_score:
                    best_score = key
                    best_i = i
            orig_idx, sb = remaining.pop(best_i)
            selected.append(sb)
            per_file[sb.block.file or ""] += 1

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "[CONTEXT_SCORER] diversified_order distinct_files=%s per_file=%s",
                distinct_files,
                dict(sorted(per_file.items(), key=lambda kv: (-kv[1], kv[0]))),
            )

        return selected

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
