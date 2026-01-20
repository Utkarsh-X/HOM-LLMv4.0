"""Token budget manager implementation."""

import logging
from typing import Optional

from homllm.context.interfaces import AllocatedBlock, BudgetConfig, ScoredBlock

logger = logging.getLogger(__name__)


class TokenBudgetManager:
    """Manages token budget allocation across blocks."""

    def allocate(
        self,
        blocks: list[ScoredBlock],
        query_features: dict,
        config: BudgetConfig,
        tokenizer: Optional[object] = None,
    ) -> list[AllocatedBlock]:
        """
        Assigns token budgets per block.
        
        Guarantees:
        - sum(allocated_tokens) <= config.max_tokens
        - Structural blocks prioritized
        - Uses same tokenizer as generation model
        """
        if not blocks:
            return []

        allocated = []
        remaining_budget = config.max_tokens

        # Sort by score (structural blocks get priority multiplier)
        sorted_blocks = sorted(
            blocks,
            key=lambda b: (
                b.structural_priority * config.structural_priority_multiplier
                + b.final_score
            ),
            reverse=True,
        )

        for scored_block in sorted_blocks:
            if remaining_budget <= 0:
                break

            block = scored_block.block
            content = block.content

            # Count tokens (use tokenizer if available, else estimate)
            if tokenizer:
                try:
                    tokens = len(tokenizer.encode(content))
                except Exception as e:
                    logger.warning(f"Tokenization failed: {e}, using estimate")
                    tokens = self._estimate_tokens(content)
            else:
                tokens = self._estimate_tokens(content)

            # Allocate tokens (don't exceed remaining budget)
            allocated_tokens = min(tokens, remaining_budget)
            remaining_budget -= allocated_tokens

            # Truncate content if needed
            if allocated_tokens < tokens:
                truncated_content = self._truncate_content(
                    content, allocated_tokens, tokenizer
                )
            else:
                truncated_content = content

            allocated_block = AllocatedBlock(
                block=block,
                allocated_tokens=allocated_tokens,
                truncated_content=truncated_content,
            )

            allocated.append(allocated_block)

        return allocated

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough: ~4 chars per token)."""
        return len(text) // 4

    def _truncate_content(
        self, content: str, max_tokens: int, tokenizer: Optional[object] = None
    ) -> str:
        """Truncate content to fit token budget."""
        if tokenizer:
            try:
                # Tokenize and truncate
                tokens = tokenizer.encode(content)
                truncated_tokens = tokens[:max_tokens]
                return tokenizer.decode(truncated_tokens)
            except Exception:
                pass

        # Fallback: character-based truncation
        estimated_chars = max_tokens * 4
        if len(content) <= estimated_chars:
            return content

        # Truncate at word boundary
        truncated = content[:estimated_chars]
        last_space = truncated.rfind("\n")
        if last_space > estimated_chars * 0.8:  # Keep if reasonable
            return truncated[:last_space] + "\n..."
        return truncated + "..."
