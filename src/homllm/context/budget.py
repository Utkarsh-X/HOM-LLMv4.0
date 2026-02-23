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
        preserve_order: bool = False,
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

        integration_pressure = float(query_features.get("integration_pressure", 0.0) or 0.0)
        # Continuous modulation factors (bounded). Preserve order; never re-rank.
        # Higher pressure => smaller per-block cap and stronger truncation for repeats/overlaps.
        base_cap_ratio = 0.50
        min_cap_ratio = 0.20
        cap_ratio = base_cap_ratio - (0.30 * integration_pressure)
        cap_ratio = min(max(cap_ratio, min_cap_ratio), base_cap_ratio)
        per_block_cap = int(max(1, cap_ratio * config.max_tokens))

        redundancy_penalty_scale = 1.0 + 0.50 * integration_pressure

        if preserve_order:
            sorted_blocks = list(blocks)
        else:
            # Sort by score (structural blocks get priority multiplier)
            sorted_blocks = sorted(
                blocks,
                key=lambda b: (
                    b.structural_priority * config.structural_priority_multiplier
                    + b.final_score
                ),
                reverse=True,
            )

        allocated_files: dict[str, int] = {}
        allocated_blocks: list[AllocatedBlock] = []

        # Token estimation telemetry: track estimated vs actual when tokenizer available
        token_estimation_errors: list[tuple[int, int]] = []  # (estimated, actual)

        for scored_block in sorted_blocks:
            if remaining_budget <= 0:
                break

            block = scored_block.block
            content = block.content

            # Count tokens (use tokenizer if available, else estimate)
            if tokenizer:
                try:
                    tokens = len(tokenizer.encode(content))
                    # Track estimation error for telemetry
                    estimated = self._estimate_tokens(content)
                    token_estimation_errors.append((estimated, tokens))
                except Exception as e:
                    logger.warning(f"Tokenization failed: {e}, using estimate")
                    tokens = self._estimate_tokens(content)
            else:
                tokens = self._estimate_tokens(content)

            # Allocate tokens (don't exceed remaining budget), with soft caps.
            local_cap = per_block_cap

            # Redundancy soft penalty based on span overlap with already allocated blocks.
            # (Continuous; no hard cutoffs.)
            redundancy_ratio = self._max_span_overlap_ratio(block, [ab.block for ab in allocated_blocks])
            if redundancy_ratio > 0:
                factor = 1.0 + (redundancy_penalty_scale - 1.0) * redundancy_ratio
                local_cap = max(1, int(local_cap / factor))

            if len(sorted_blocks) <= 1:
                allocated_tokens = min(tokens, remaining_budget)
            else:
                allocated_tokens = min(tokens, remaining_budget, local_cap)
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
            allocated_blocks.append(allocated_block)
            if block.file:
                allocated_files[block.file] = allocated_files.get(block.file, 0) + 1

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "[BUDGET] file=%s file_count=%s tokens=%s cap=%s allocated=%s remaining=%s overlap=%.3f",
                    block.file,
                    allocated_files.get(block.file, 0) if block.file else 0,
                    tokens,
                    local_cap,
                    allocated_tokens,
                    remaining_budget,
                    float(redundancy_ratio),
                )

        # Log token estimation telemetry
        if token_estimation_errors:
            total_estimated = sum(e for e, _ in token_estimation_errors)
            total_actual = sum(a for _, a in token_estimation_errors)
            errors = [e - a for e, a in token_estimation_errors]
            mean_error = sum(errors) / len(errors) if errors else 0
            max_error = max(abs(err) for err in errors) if errors else 0
            logger.info(
                "[BUDGET_TELEMETRY] tokenizer=active blocks=%s estimated_total=%s actual_total=%s "
                "delta=%s mean_block_error=%.1f max_block_error=%s",
                len(token_estimation_errors), total_estimated, total_actual,
                total_estimated - total_actual, mean_error, max_error,
            )
        else:
            logger.info("[BUDGET_TELEMETRY] tokenizer=fallback(len//4)")

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "[BUDGET] done selected_blocks=%s used_tokens=%s max_tokens=%s per_file=%s",
                len(allocated_blocks),
                sum(ab.allocated_tokens for ab in allocated_blocks),
                config.max_tokens,
                dict(sorted(allocated_files.items(), key=lambda kv: (-kv[1], kv[0]))),
            )

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

    def _max_span_overlap_ratio(self, block, prior_blocks) -> float:
        if not prior_blocks:
            return 0.0
        best = 0.0
        for other in prior_blocks:
            best = max(best, self._span_overlap_ratio(block, other))
        return best

    def _span_overlap_ratio(self, a, b) -> float:
        if a.file != b.file:
            return 0.0
        if a.start_line is None or a.end_line is None:
            return 0.0
        if b.start_line is None or b.end_line is None:
            return 0.0
        start = max(int(a.start_line), int(b.start_line))
        end = min(int(a.end_line), int(b.end_line))
        if start > end:
            return 0.0
        overlap = end - start + 1
        length = min(
            max(int(a.end_line) - int(a.start_line) + 1, 1),
            max(int(b.end_line) - int(b.start_line) + 1, 1),
        )
        return overlap / length
