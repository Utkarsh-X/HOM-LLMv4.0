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

            # Structural priority from ranking trace (entry points, decorators, etc.)
            trace = debug_traces.get(block.block_id)
            structural_priority = float(trace.struct_bonus) if trace else 0.0
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

    # ── Tier 2: Coherence refinement (post-lock) ────────────────────────

    def compute_coherence_refinement(
        self,
        scored_blocks: list[ScoredBlock],
        callgraph: dict[str, list[str]],
        config: "ContextConfig",
    ) -> list[ScoredBlock]:
        """Post-lock coherence refinement. Adjusts mid-range (position N+) only.

        Computes four deterministic signals per-block:
          1. Same-file adjacency bonus
          2. Call-chain adjacency bonus
          3. Redundancy synergy (Jaccard overlap → bonus instead of penalty)
          4. Light dispersion penalty

        Coherence contribution is capped at `config.coherence_max_contribution`
        fraction of each block's base score. Top-N blocks are protected.
        """
        if not getattr(config, "coherence_enabled", False):
            return scored_blocks

        n = len(scored_blocks)
        if n <= 1:
            return scored_blocks

        protect_n = getattr(config, "coherence_protect_top_n", 3)
        max_contrib = getattr(config, "coherence_max_contribution", 0.15)
        proximity_lines = getattr(config, "coherence_proximity_lines", 50)
        synergy_thresh = getattr(config, "coherence_synergy_threshold", 0.3)
        dispersion_thresh = getattr(config, "coherence_dispersion_threshold", 0.9)
        cg_bonus = getattr(config, "coherence_callgraph_bonus", 0.1)
        same_file_bonus = getattr(config, "coherence_same_file_bonus", 0.8)

        # Precompute token sets for synergy scoring
        token_sets: list[set[str]] = []
        for sb in scored_blocks:
            content = sb.block.content or ""
            token_sets.append(set(content.lower().split()))

        # Build reverse callgraph (callee → callers)
        reverse_cg: dict[str, list[str]] = {}
        for caller, callees in callgraph.items():
            for callee in callees:
                if callee not in reverse_cg:
                    reverse_cg[callee] = []
                reverse_cg[callee].append(caller)

        # Precompute file dispersion ratio
        unique_files = len({sb.block.file for sb in scored_blocks if sb.block.file})
        dispersion_ratio = unique_files / n if n > 0 else 0.0

        # Compute coherence score for each block
        coherence_scores: list[float] = []
        coherence_details: list[dict] = []

        for i, sb in enumerate(scored_blocks):
            same_file_adj = 0.0
            call_chain_adj = 0.0
            synergy_total = 0.0
            dispersion_pen = 0.0

            for j, other in enumerate(scored_blocks):
                if i == j:
                    continue

                # 1. Same-file adjacency bonus
                if sb.block.file and sb.block.file == other.block.file:
                    line_dist = abs(sb.block.start_line - other.block.start_line)
                    if line_dist <= proximity_lines:
                        decay = 1.0 - (line_dist / proximity_lines)
                        same_file_adj = max(same_file_adj, same_file_bonus * decay)

                # 2. Call-chain adjacency bonus
                sid = sb.block.symbol_id or ""
                oid = other.block.symbol_id or ""
                if sid and oid:
                    # Direct: sb calls other, or other calls sb
                    if oid in callgraph.get(sid, []) or sid in callgraph.get(oid, []):
                        call_chain_adj = max(call_chain_adj, cg_bonus)

                # 3. Redundancy synergy
                if token_sets[i] and token_sets[j]:
                    inter = len(token_sets[i] & token_sets[j])
                    union = len(token_sets[i] | token_sets[j])
                    jaccard = inter / union if union > 0 else 0.0
                    if jaccard >= synergy_thresh:
                        synergy_total = max(synergy_total, jaccard * 0.1)

            # 4. Light dispersion penalty
            if dispersion_ratio > dispersion_thresh:
                dispersion_pen = -0.02 * (dispersion_ratio - dispersion_thresh) / (1.0 - dispersion_thresh + 1e-9)

            raw_coherence = same_file_adj + call_chain_adj + synergy_total + dispersion_pen

            # Cap at max_contribution fraction of base final_score
            cap = abs(sb.final_score) * max_contrib
            capped_coherence = max(-cap, min(cap, raw_coherence))

            coherence_scores.append(capped_coherence)
            coherence_details.append({
                "same_file_bonus": round(same_file_adj, 4),
                "call_chain_bonus": round(call_chain_adj, 4),
                "synergy_bonus": round(synergy_total, 4),
                "dispersion_penalty": round(dispersion_pen, 4),
                "raw": round(raw_coherence, 4),
                "capped": round(capped_coherence, 4),
            })

        # Build updated scored blocks: top-N protected, rest re-sorted by adjusted score
        protected = []
        refinable = []
        for i, sb in enumerate(scored_blocks):
            new_sb = ScoredBlock(
                block=sb.block,
                semantic_score=sb.semantic_score,
                name_score=sb.name_score,
                structural_priority=sb.structural_priority,
                novelty_score=sb.novelty_score,
                coherence_score=coherence_scores[i],
                final_score=sb.final_score + coherence_scores[i],
            )
            if i < protect_n:
                protected.append(new_sb)
            else:
                refinable.append(new_sb)

        # Sort only the refinable portion by adjusted final_score (descending)
        refinable.sort(key=lambda sb: sb.final_score, reverse=True)

        result = protected + refinable

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "[COHERENCE_REFINEMENT] protect_top=%d, refined=%d, "
                "max_coherence=%.4f, min_coherence=%.4f",
                len(protected),
                len(refinable),
                max(coherence_scores) if coherence_scores else 0.0,
                min(coherence_scores) if coherence_scores else 0.0,
            )

        # Store details for telemetry (pipeline reads this)
        self._last_coherence_details = coherence_details

        return result

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
