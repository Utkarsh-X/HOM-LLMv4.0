"""Constrained set optimization for ranking selection."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import logging
import math
from typing import Optional

from homllm.retrieval.interfaces import Candidate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SetObjectiveWeights:
    """Weights for set-level objective components."""

    relevance: float
    structural_coherence: float
    coverage: float
    redundancy: float
    dispersion: float


@dataclass(frozen=True)
class SetOptimizationMetrics:
    """Telemetry for set optimization."""

    objective: float
    relevance: float
    structural_coherence: float
    coverage: float
    redundancy: float
    dispersion: float
    tokens_used: int
    blocks_selected: int
    marginal_gain_sequence: list[float]
    weight_vector_used: dict[str, float]
    redundancy_penalty_mean: float = 0.0
    dispersion_bonus_mean: float = 0.0
    objective_term_contributions: dict[str, float] = field(default_factory=dict)
    topK_file_entropy_post_selection: float | None = None
    topK_unique_file_count_post_selection: int | None = None
    topK_max_file_block_ratio_post_selection: float | None = None
    marginal_gain_breakdown: list[dict[str, float]] = field(default_factory=list)
    round_trace: list[dict[str, object]] = field(default_factory=list)
    base_weight_vector: dict[str, float] | None = None
    effective_weight_vector: dict[str, float] | None = None
    final_distinct_file_count: int | None = None


class SetOptimizer:
    """Greedy marginal-gain optimizer under a token budget."""

    def __init__(
        self,
        token_budget: int,
        weights: SetObjectiveWeights,
        callgraph: Optional[dict] = None,
        concentration_top_k: int = 10,
        max_rounds: int = 100,
    ) -> None:
        self.token_budget = token_budget
        self.weights = weights
        self.callgraph = callgraph or {}
        self.concentration_top_k = max(int(concentration_top_k), 1)
        self.max_rounds = max(int(max_rounds), 1)

    def select(
        self,
        candidates: list[Candidate],
        relevance_map: dict[str, float],
        query_concepts: list[str],
    ) -> tuple[list[Candidate], SetOptimizationMetrics]:
        if not candidates:
            return [], SetOptimizationMetrics(
                objective=0.0,
                relevance=0.0,
                structural_coherence=0.0,
                coverage=0.0,
                redundancy=0.0,
                dispersion=0.0,
                tokens_used=0,
                blocks_selected=0,
                marginal_gain_sequence=[],
                marginal_gain_breakdown=[],
                round_trace=[],
                weight_vector_used=self._weights_dict(),
                base_weight_vector=self._weights_dict(),
                effective_weight_vector=self._weights_dict(),
            )

        selected: list[Candidate] = []
        remaining = list(candidates)
        budget_left = self.token_budget
        marginal_gains: list[float] = []
        marginal_gain_breakdown: list[dict[str, float]] = []
        round_trace: list[dict[str, object]] = []
        accepted_redundancy_penalties: list[float] = []
        accepted_dispersion_bonuses: list[float] = []

        p50_tokens = self._p50_candidate_tokens(candidates)
        max_candidates = max(
            1,
            min(len(candidates), int(self.token_budget / max(1, p50_tokens))),
        )
        if len(candidates) >= 2 and max_candidates < 2:
            max_candidates = 2

        concept_set = {c.lower() for c in query_concepts if c}
        concept_hits: dict[str, set[str]] = {}
        for cand in remaining:
            concept_hits[cand.doc_id] = self._concepts_for_candidate(cand, concept_set)

        # Pre-compute and cache pairwise span overlaps (immutable per candidate pair)
        self._overlap_cache: dict[tuple[str, str], float] = {}

        rounds = 0

        # -------------------------------------------------------------------
        # CELF (Cost-Effective Lazy Forward) greedy selection.
        #
        # Key insight: for approximately-submodular objectives, marginal gains
        # are non-increasing as more items are selected. So after the initial
        # full scan (round 0), we only need to re-evaluate the top candidate
        # from a max-heap. If its re-evaluated gain is still the best, select
        # it immediately; otherwise push it back and try the next one.
        #
        # Complexity: O(N) for round 0, then O(~2 × log N) per subsequent
        # round vs O(N) per round for brute-force. Typical 10-50× speedup.
        # -------------------------------------------------------------------
        import heapq

        # Round 0: full scan to seed the heap with initial marginal gains.
        current_metrics = self._compute_metrics(
            selected, relevance_map, concept_set, concept_hits, max_candidates,
        )
        current_obj = self._objective(current_metrics, self.weights)

        # Max-heap entries: (-gain, candidate_index_in_remaining, eval_round)
        # Python heapq is a min-heap, so negate gain for max-heap behavior.
        heap: list[tuple[float, int, int]] = []
        remaining_map: dict[int, Candidate] = {}

        for idx, cand in enumerate(remaining):
            cost = self._estimate_tokens(cand)
            if cost > budget_left:
                continue

            tentative = selected + [cand]
            tentative_metrics = self._compute_metrics(
                tentative, relevance_map, concept_set, concept_hits,
                max_candidates,
            )
            gain, tentative_obj = self._marginal_gain(
                current_metrics=current_metrics,
                current_obj=current_obj,
                tentative_metrics=tentative_metrics,
            )
            components = self._component_contributions(tentative_metrics)

            # Record telemetry for first 10 evaluations
            if len(marginal_gain_breakdown) < 10:
                self._record_breakdown(
                    marginal_gain_breakdown, gain, tentative_metrics,
                    current_obj, tentative_obj,
                )
            round_trace.append(
                {
                    "event": "eval",
                    "phase": "round0_seed",
                    "round": 0,
                    "candidate_id": cand.doc_id,
                    "gain": float(gain),
                    "current_obj": float(current_obj),
                    "tentative_obj": float(tentative_obj),
                    "budget_left_before": int(budget_left),
                    "candidate_tokens": int(cost),
                    "components": components,
                }
            )

            remaining_map[idx] = cand
            heapq.heappush(heap, (-gain, idx, 0))

        # Greedy selection rounds using CELF lazy evaluation.
        while heap and rounds < self.max_rounds:
            neg_gain, best_idx, eval_round = heapq.heappop(heap)

            # If this entry was evaluated in the current round, it's fresh.
            if eval_round == rounds:
                gain = -neg_gain
                if gain <= 0:
                    break  # No positive marginal gain left

                cand = remaining_map.pop(best_idx)
                selected.append(cand)
                budget_left -= self._estimate_tokens(cand)

                # Compute metrics for the chosen candidate (for telemetry)
                chosen_metrics = self._compute_metrics(
                    selected, relevance_map, concept_set, concept_hits,
                    max_candidates,
                )
                accepted_redundancy_penalties.append(
                    self.weights.redundancy * chosen_metrics["redundancy_penalty"]
                )
                accepted_dispersion_bonuses.append(
                    self.weights.dispersion * chosen_metrics["dispersion_bonus"]
                )
                if len(marginal_gains) < 10:
                    marginal_gains.append(gain)

                # Update current objective for next round's lazy evaluations.
                current_metrics = chosen_metrics
                current_obj = self._objective(chosen_metrics, self.weights)
                round_trace.append(
                    {
                        "event": "select",
                        "round": int(rounds),
                        "candidate_id": cand.doc_id,
                        "gain": float(gain),
                        "current_obj": float(current_obj),
                        "budget_left_after": int(budget_left),
                        "selected_count": len(selected),
                        "components_after_select": self._component_contributions(chosen_metrics),
                    }
                )
                rounds += 1

                # Prune heap: remove entries that can no longer fit budget.
                pruned: list[tuple[float, int, int]] = []
                for entry in heap:
                    _, entry_idx, _ = entry
                    if entry_idx in remaining_map:
                        entry_cand = remaining_map[entry_idx]
                        if self._estimate_tokens(entry_cand) <= budget_left:
                            pruned.append(entry)
                heapq.heapify(pruned)
                heap = pruned

            else:
                # Stale entry: re-evaluate with current selected set.
                if best_idx not in remaining_map:
                    continue  # Already selected or removed

                cand = remaining_map[best_idx]
                if self._estimate_tokens(cand) > budget_left:
                    del remaining_map[best_idx]
                    continue

                tentative = selected + [cand]
                tentative_metrics = self._compute_metrics(
                    tentative, relevance_map, concept_set, concept_hits,
                    max_candidates,
                )
                fresh_gain, tentative_obj = self._marginal_gain(
                    current_metrics=current_metrics,
                    current_obj=current_obj,
                    tentative_metrics=tentative_metrics,
                )
                components = self._component_contributions(tentative_metrics)

                # Record telemetry for first 10
                if len(marginal_gain_breakdown) < 10:
                    self._record_breakdown(
                        marginal_gain_breakdown, fresh_gain, tentative_metrics,
                        current_obj, tentative_obj,
                    )
                round_trace.append(
                    {
                        "event": "eval",
                        "phase": "lazy_reeval",
                        "round": int(rounds),
                        "candidate_id": cand.doc_id,
                        "gain": float(fresh_gain),
                        "current_obj": float(current_obj),
                        "tentative_obj": float(tentative_obj),
                        "budget_left_before": int(budget_left),
                        "candidate_tokens": int(self._estimate_tokens(cand)),
                        "components": components,
                    }
                )

                heapq.heappush(heap, (-fresh_gain, best_idx, rounds))

        if not selected and remaining:
            fallback = None
            fallback_score = None
            for cand in remaining:
                if self._estimate_tokens(cand) > budget_left:
                    continue
                score = relevance_map.get(cand.doc_id, 0.0)
                if fallback is None or score > (fallback_score or 0.0):
                    fallback = cand
                    fallback_score = score
            if fallback is not None:
                selected.append(fallback)
                budget_left -= self._estimate_tokens(fallback)
                round_trace.append(
                    {
                        "event": "fallback_select",
                        "round": int(rounds),
                        "candidate_id": fallback.doc_id,
                        "budget_left_after": int(budget_left),
                        "reason": "no_positive_marginal_gain",
                    }
                )

        final_metrics = self._compute_metrics(
            selected,
            relevance_map,
            concept_set,
            concept_hits,
            max_candidates,
        )
        final_obj = self._objective(final_metrics, self.weights)
        distinct_files = len({c.file for c in selected if c.file}) if selected else 0
        weight_vector = self._weights_dict()
        concentration_post = self._topk_file_concentration_metrics(
            selected,
            self.concentration_top_k,
        )
        objective_term_contributions = {
            "relevance": self.weights.relevance * final_metrics["relevance"],
            "structural_coherence": self.weights.structural_coherence
            * final_metrics["structural_coherence"],
            "coverage": self.weights.coverage * final_metrics["coverage"],
            "redundancy_penalty": self.weights.redundancy
            * final_metrics["redundancy_penalty"],
            "dispersion_bonus": self.weights.dispersion
            * final_metrics["dispersion_bonus"],
            "total_objective": final_obj,
        }
        logger.debug(
            "[SET_OPT_FINAL] objective=%.6f relevance=%.6f structural=%.6f "
            "coverage=%.6f redundancy_penalty=%.6f dispersion_bonus=%.6f "
            "weights=%s",
            final_obj,
            objective_term_contributions["relevance"],
            objective_term_contributions["structural_coherence"],
            objective_term_contributions["coverage"],
            objective_term_contributions["redundancy_penalty"],
            objective_term_contributions["dispersion_bonus"],
            weight_vector,
        )
        metrics = SetOptimizationMetrics(
            objective=final_obj,
            relevance=final_metrics["relevance"],
            structural_coherence=final_metrics["structural_coherence"],
            coverage=final_metrics["coverage"],
            redundancy=final_metrics["redundancy_penalty"],
            dispersion=final_metrics["dispersion_bonus"],
            redundancy_penalty_mean=(
                sum(accepted_redundancy_penalties)
                / len(accepted_redundancy_penalties)
                if accepted_redundancy_penalties
                else 0.0
            ),
            dispersion_bonus_mean=(
                sum(accepted_dispersion_bonuses)
                / len(accepted_dispersion_bonuses)
                if accepted_dispersion_bonuses
                else 0.0
            ),
            objective_term_contributions=objective_term_contributions,
            topK_file_entropy_post_selection=concentration_post[
                "topK_file_entropy"
            ],
            topK_unique_file_count_post_selection=concentration_post[
                "topK_unique_file_count"
            ],
            topK_max_file_block_ratio_post_selection=concentration_post[
                "max_file_block_ratio"
            ],
            tokens_used=final_metrics["tokens_used"],
            blocks_selected=len(selected),
            marginal_gain_sequence=marginal_gains,
            marginal_gain_breakdown=marginal_gain_breakdown,
            round_trace=round_trace,
            weight_vector_used=weight_vector,
            base_weight_vector=weight_vector,
            effective_weight_vector=weight_vector,
            final_distinct_file_count=distinct_files,
        )
        return selected, metrics

    def _marginal_gain(
        self,
        *,
        current_metrics: dict[str, float],
        current_obj: float,
        tentative_metrics: dict[str, float],
    ) -> tuple[float, float]:
        """
        Compute marginal gain with non-negative dispersion contribution.

        We still reward dispersion increases, but we do not let a dispersion drop
        alone make additional same-file evidence look worse than the current set.
        """
        tentative_obj_raw = self._objective(tentative_metrics, self.weights)

        current_disp = self.weights.dispersion * current_metrics["dispersion_bonus"]
        tentative_disp = self.weights.dispersion * tentative_metrics["dispersion_bonus"]
        dispersion_delta = tentative_disp - current_disp

        adjusted_tentative_obj = tentative_obj_raw
        if dispersion_delta < 0.0:
            adjusted_tentative_obj -= dispersion_delta

        return adjusted_tentative_obj - current_obj, adjusted_tentative_obj

    def _objective(self, metrics: dict[str, float], weights: SetObjectiveWeights) -> float:
        return (
            weights.relevance * metrics["relevance"]
            + weights.structural_coherence * metrics["structural_coherence"]
            + weights.coverage * metrics["coverage"]
            - weights.redundancy * metrics["redundancy_penalty"]
            + weights.dispersion * metrics["dispersion_bonus"]
        )

    def _record_breakdown(
        self,
        breakdown_list: list[dict[str, float]],
        gain: float,
        tentative_metrics: dict[str, float],
        current_obj: float,
        tentative_obj: float,
    ) -> None:
        """Record marginal gain breakdown telemetry for a candidate evaluation."""
        relevance_contribution = self.weights.relevance * tentative_metrics["relevance"]
        structural_contribution = (
            self.weights.structural_coherence * tentative_metrics["structural_coherence"]
        )
        coverage_contribution = self.weights.coverage * tentative_metrics["coverage"]
        redundancy_penalty = self.weights.redundancy * tentative_metrics["redundancy_penalty"]
        dispersion_bonus = self.weights.dispersion * tentative_metrics["dispersion_bonus"]
        breakdown_list.append({
            "gain": gain,
            "relevance": relevance_contribution,
            "coverage": coverage_contribution,
            "structural": structural_contribution,
            "redundancy_penalty": redundancy_penalty,
            "dispersion_bonus": dispersion_bonus,
        })
        logger.debug(
            "[SET_OPT_GAIN] current_obj=%.6f tentative_obj=%.6f gain=%.6f "
            "relevance=%.6f structural=%.6f coverage=%.6f redundancy_penalty=%.6f dispersion_bonus=%.6f",
            current_obj, tentative_obj, gain,
            relevance_contribution, structural_contribution, coverage_contribution,
            redundancy_penalty, dispersion_bonus,
        )

    def _component_contributions(self, metrics: dict[str, float]) -> dict[str, float]:
        return {
            "relevance": float(self.weights.relevance * metrics["relevance"]),
            "structural_coherence": float(
                self.weights.structural_coherence * metrics["structural_coherence"]
            ),
            "coverage": float(self.weights.coverage * metrics["coverage"]),
            "redundancy_penalty": float(
                self.weights.redundancy * metrics["redundancy_penalty"]
            ),
            "dispersion_bonus": float(
                self.weights.dispersion * metrics["dispersion_bonus"]
            ),
        }

    def _compute_metrics(
        self,
        selected: list[Candidate],
        relevance_map: dict[str, float],
        concept_set: set[str],
        concept_hits: dict[str, set[str]],
        max_candidates: int,
    ) -> dict[str, float]:
        if not selected:
            return {
                "relevance": 0.0,
                "structural_coherence": 0.0,
                "coverage": 0.0,
                "redundancy_penalty": 0.0,
                "dispersion_bonus": 0.0,
                "redundancy": 0.0,
                "dispersion": 0.0,
                "tokens_used": 0.0,
            }

        relevance = self._relevance(selected, relevance_map, max_candidates)
        structural_coherence = self._structural_coherence(selected)
        coverage = self._coverage(selected, concept_set, concept_hits)
        redundancy_penalty = self._redundancy(selected)
        dispersion_bonus = self._dispersion_bonus(selected)
        tokens_used = sum(self._estimate_tokens(c) for c in selected)

        return {
            "relevance": self._clamp01(relevance),
            "structural_coherence": self._clamp01(structural_coherence),
            "coverage": self._clamp01(coverage),
            "redundancy_penalty": self._clamp01(redundancy_penalty),
            "dispersion_bonus": self._clamp01(dispersion_bonus),
            # Compatibility aliases for existing telemetry consumers.
            "redundancy": self._clamp01(redundancy_penalty),
            "dispersion": self._clamp01(dispersion_bonus),
            "tokens_used": float(tokens_used),
        }

    def _relevance(
        self,
        selected: list[Candidate],
        relevance_map: dict[str, float],
        max_candidates: int,
    ) -> float:
        if not selected:
            return 0.0
        total = 0.0
        for c in selected:
            total += relevance_map.get(c.doc_id, 0.0)
        return total / max(max_candidates, 1)

    def _structural_coherence(self, selected: list[Candidate]) -> float:
        symbols = [c.symbol_id for c in selected if c.symbol_id]
        if len(symbols) < 2:
            return 0.0
        edges = 0
        possible = len(symbols) * (len(symbols) - 1)
        symbol_set = set(symbols)
        for sym in symbols:
            for neighbor in self.callgraph.get(sym, []):
                if neighbor in symbol_set:
                    edges += 1
        edge_density = edges / max(possible, 1)
        return min(edge_density, 1.0)

    def _coverage(
        self,
        selected: list[Candidate],
        concept_set: set[str],
        concept_hits: dict[str, set[str]],
    ) -> float:
        if not concept_set:
            return 0.0
        covered = set()
        for cand in selected:
            covered |= concept_hits.get(cand.doc_id, set())
        return len(covered) / max(len(concept_set), 1)

    def _redundancy(self, selected: list[Candidate]) -> float:
        if len(selected) < 2:
            return 0.0
        symbol_ids = [c.symbol_id for c in selected if c.symbol_id]
        symbol_dup = 1.0 - (len(set(symbol_ids)) / max(len(symbol_ids), 1)) if symbol_ids else 0.0
        span_overlap = self._avg_span_overlap(selected)
        return min(1.0, 0.6 * span_overlap + 0.4 * symbol_dup)

    def _dispersion_bonus(self, selected: list[Candidate]) -> float:
        """
        Soft dispersion bonus in [0, 1].

        Monotonic in both:
        - unique file coverage ratio
        - normalized file entropy
        """
        if not selected:
            return 0.0
        selected_count = len(selected)
        # No diversity signal for a singleton set.
        if selected_count <= 1:
            return 0.0
        file_keys = [
            str(c.file) if c.file else f"__unknown__:{c.doc_id}"
            for c in selected
        ]
        counts = Counter(file_keys)
        distinct_files = len(counts)
        if selected_count <= 0:
            return 0.0
        # Normalize unique ratio so:
        # - one file repeated => 0
        # - every added item from a new file => 1
        unique_ratio = (distinct_files - 1) / float(selected_count - 1)
        if distinct_files <= 1:
            entropy = 0.0
        else:
            probs = [cnt / float(selected_count) for cnt in counts.values()]
            raw_entropy = -sum(p * math.log(p) for p in probs if p > 0.0)
            entropy = raw_entropy / math.log(float(distinct_files))
        return self._clamp01(0.5 * unique_ratio + 0.5 * entropy)

    def _avg_span_overlap(self, selected: list[Candidate]) -> float:
        overlaps = []
        for i, a in enumerate(selected):
            for b in selected[i + 1:]:
                overlaps.append(self._span_overlap_ratio_cached(a, b))
        if not overlaps:
            return 0.0
        return sum(overlaps) / len(overlaps)

    def _span_overlap_ratio_cached(self, a: Candidate, b: Candidate) -> float:
        """Cached pairwise span overlap. Results are immutable per candidate pair."""
        key = (a.doc_id, b.doc_id) if a.doc_id <= b.doc_id else (b.doc_id, a.doc_id)
        cache = getattr(self, "_overlap_cache", None)
        if cache is not None and key in cache:
            return cache[key]
        result = self._span_overlap_ratio(a, b)
        if cache is not None:
            cache[key] = result
        return result

    def _span_overlap_ratio(self, a: Candidate, b: Candidate) -> float:
        if a.file != b.file:
            return 0.0
        if a.span_start is None or a.span_end is None:
            return 0.0
        if b.span_start is None or b.span_end is None:
            return 0.0
        start = max(a.span_start, b.span_start)
        end = min(a.span_end, b.span_end)
        if start > end:
            return 0.0
        overlap = end - start + 1
        length = min(
            max(a.span_end - a.span_start + 1, 1),
            max(b.span_end - b.span_start + 1, 1),
        )
        return overlap / length

    def _concepts_for_candidate(
        self, candidate: Candidate, concept_set: set[str]
    ) -> set[str]:
        if not concept_set:
            return set()
        haystack = " ".join(
            [
                candidate.file or "",
                candidate.symbol_id or "",
                (candidate.content or "")[:300],
            ]
        ).lower()
        hits = {c for c in concept_set if c in haystack}
        return hits

    def _estimate_tokens(self, candidate: Candidate) -> int:
        if candidate.content:
            return max(1, len(candidate.content) // 4)
        return 50

    def _p50_candidate_tokens(self, candidates: list[Candidate]) -> int:
        if not candidates:
            return 0
        sizes = sorted(self._estimate_tokens(c) for c in candidates)
        mid = len(sizes) // 2
        if len(sizes) % 2 == 0:
            return int((sizes[mid - 1] + sizes[mid]) / 2)
        return sizes[mid]

    def _weights_dict(self) -> dict[str, float]:
        return {
            "relevance": self.weights.relevance,
            "structural_coherence": self.weights.structural_coherence,
            "coverage": self.weights.coverage,
            "redundancy": self.weights.redundancy,
            "dispersion": self.weights.dispersion,
        }

    def _topk_file_concentration_metrics(
        self,
        selected: list[Candidate],
        top_k: int,
    ) -> dict[str, float | int]:
        if not selected:
            return {
                "top_k": 0,
                "topK_unique_file_count": 0,
                "topK_file_entropy": 0.0,
                "max_file_block_ratio": 0.0,
            }
        k = min(max(int(top_k), 1), len(selected))
        subset = selected[:k]
        file_keys = [
            str(c.file) if c.file else f"__unknown__:{c.doc_id}"
            for c in subset
        ]
        counts = Counter(file_keys)
        unique_files = len(counts)
        max_ratio = max(counts.values()) / float(k) if counts else 0.0
        if unique_files <= 1:
            entropy = 0.0
        else:
            probs = [cnt / float(k) for cnt in counts.values()]
            raw_entropy = -sum(p * math.log(p) for p in probs if p > 0.0)
            entropy = raw_entropy / math.log(float(unique_files))
        return {
            "top_k": k,
            "topK_unique_file_count": unique_files,
            "topK_file_entropy": self._clamp01(entropy),
            "max_file_block_ratio": self._clamp01(max_ratio),
        }

    def _clamp01(self, value: float) -> float:
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value


def extract_query_concepts(query: str) -> list[str]:
    """Generic, query-agnostic concept extraction."""
    import re

    tokens = re.findall(r"\b[A-Za-z0-9_]+\b", query)
    l_levels = re.findall(r"\bL\d+\b", query)
    tokens.extend(l_levels)
    stopwords = {
        "what", "when", "where", "which", "who", "whom", "why", "how",
        "does", "do", "did", "is", "are", "was", "were", "be", "been",
        "the", "a", "an", "and", "or", "but", "if", "then", "than",
        "this", "that", "these", "those", "with", "without", "about",
        "into", "from", "to", "of", "for", "in", "on", "at", "by",
        "all", "any", "each", "every", "some", "most", "many", "few",
        "explain", "describe", "show", "tell", "trace", "resolve",
    }
    concepts = []
    seen = set()
    for token in tokens:
        if len(token) < 2:
            continue
        token_lower = token.lower()
        if token_lower in stopwords:
            continue
        if token_lower not in seen:
            seen.add(token_lower)
            concepts.append(token)
    return concepts
