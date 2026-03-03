"""Token budget manager implementation."""

import logging
from typing import Optional

from homllm.context.interfaces import AllocatedBlock, BudgetConfig, ScoredBlock

logger = logging.getLogger(__name__)


class TokenBudgetManager:
    """Manages token budget allocation across blocks."""

    def __init__(self):
        # Populated after each allocate() for pipeline telemetry
        self._last_utilization_diagnostic: dict | None = None

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

        # Utilization diagnostic accumulators
        offered_tokens_total = 0
        cap_limited_total = 0
        budget_limited_total = 0

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

            # Track where tokens are lost
            offered_tokens_total += tokens
            if tokens > local_cap:
                cap_limited_total += tokens - local_cap
            remaining_after_cap = min(tokens, local_cap)
            if remaining_after_cap > remaining_budget:
                budget_limited_total += remaining_after_cap - remaining_budget

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

        # Build utilization diagnostic
        self._finalize_utilization_diagnostic(
            config, sorted_blocks, allocated_blocks, cap_ratio, per_block_cap,
            offered_tokens_total, cap_limited_total, budget_limited_total,
        )

        return allocated

    def _finalize_utilization_diagnostic(
        self, config, blocks, allocated_blocks, cap_ratio, per_block_cap,
        offered_tokens_total, cap_limited_total, budget_limited_total,
    ) -> None:
        """Build utilization diagnostic for pipeline telemetry."""
        final_tokens = sum(ab.allocated_tokens for ab in allocated_blocks)
        unused = config.max_tokens - final_tokens
        util_pct = final_tokens / max(config.max_tokens, 1) * 100

        # Classify root cause
        if len(blocks) <= 3 and offered_tokens_total < config.max_tokens * 0.5:
            classification = "Candidate Scarcity"
        elif cap_limited_total > budget_limited_total and cap_limited_total > offered_tokens_total * 0.1:
            classification = "Cap-Limited"
        elif budget_limited_total > 0:
            classification = "Budget-Limited"
        elif util_pct >= 60:
            classification = "Healthy"
        else:
            classification = "Candidate Scarcity"

        self._last_utilization_diagnostic = {
            "offered_tokens": offered_tokens_total,
            "cap_limited_tokens": cap_limited_total,
            "budget_limited_tokens": budget_limited_total,
            "final_tokens": final_tokens,
            "unused_tokens": unused,
            "candidate_count": len(blocks),
            "selected_block_count": len(allocated_blocks),
            "per_block_cap_ratio": round(cap_ratio, 3),
            "per_block_cap": per_block_cap,
            "utilization_pct": round(util_pct, 1),
            "classification": classification,
        }

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

        # Fallback: character-based truncation at code boundaries
        estimated_chars = max_tokens * 4
        if len(content) <= estimated_chars:
            return content

        truncated = content[:estimated_chars]

        # Prefer cutting at statement boundaries to preserve syntactic completeness
        # Try: blank line, then def/class boundary, then any newline
        for marker in ["\n\n", "\ndef ", "\nclass ", "\n"]:
            pos = truncated.rfind(marker)
            if pos > estimated_chars * 0.6:
                return truncated[:pos] + "\n# ... truncated"
        return truncated + "\n# ... truncated"

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
