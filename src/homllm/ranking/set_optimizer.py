"""Constrained set optimization for ranking selection."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
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
    marginal_gain_breakdown: list[dict[str, float]] = field(default_factory=list)
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
    ) -> None:
        self.token_budget = token_budget
        self.weights = weights
        self.callgraph = callgraph or {}

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
                weight_vector_used=self._weights_dict(),
                base_weight_vector=self._weights_dict(),
                effective_weight_vector=self._weights_dict(),
            )

        selected: list[Candidate] = []
        remaining = list(candidates)
        budget_left = self.token_budget
        marginal_gains: list[float] = []
        marginal_gain_breakdown: list[dict[str, float]] = []

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

        while remaining:
            best_gain = 0.0
            best_idx = None

            current_metrics = self._compute_metrics(
                selected,
                relevance_map,
                concept_set,
                concept_hits,
                max_candidates,
            )
            current_obj = self._objective(current_metrics, self.weights)

            for idx, cand in enumerate(remaining):
                cost = self._estimate_tokens(cand)
                if cost > budget_left:
                    continue

                tentative = selected + [cand]
                tentative_metrics = self._compute_metrics(
                    tentative,
                    relevance_map,
                    concept_set,
                    concept_hits,
                    max_candidates,
                )
                tentative_obj = self._objective(tentative_metrics, self.weights)
                gain = tentative_obj - current_obj

                if len(marginal_gain_breakdown) < 10:
                    relevance_contribution = self.weights.relevance * tentative_metrics["relevance"]
                    structural_contribution = (
                        self.weights.structural_coherence
                        * tentative_metrics["structural_coherence"]
                    )
                    coverage_contribution = self.weights.coverage * tentative_metrics["coverage"]
                    redundancy_penalty = self.weights.redundancy * tentative_metrics["redundancy"]
                    dispersion_penalty = self.weights.dispersion * tentative_metrics["dispersion"]
                    marginal_gain_breakdown.append(
                        {
                            "gain": gain,
                            "relevance": relevance_contribution,
                            "coverage": coverage_contribution,
                            "structural": structural_contribution,
                            "redundancy_penalty": redundancy_penalty,
                            "dispersion_penalty": dispersion_penalty,
                        }
                    )
                    logger.debug(
                        "[SET_OPT_GAIN] current_obj=%.6f tentative_obj=%.6f gain=%.6f "
                        "relevance=%.6f structural=%.6f coverage=%.6f redundancy_penalty=%.6f dispersion_penalty=%.6f",
                        current_obj,
                        tentative_obj,
                        gain,
                        relevance_contribution,
                        structural_contribution,
                        coverage_contribution,
                        redundancy_penalty,
                        dispersion_penalty,
                    )

                if gain > best_gain:
                    best_gain = gain
                    best_idx = idx

            if best_idx is None or best_gain <= 0:
                break

            chosen = remaining.pop(best_idx)
            selected.append(chosen)
            budget_left -= self._estimate_tokens(chosen)
            if len(marginal_gains) < 10:
                marginal_gains.append(best_gain)

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
        metrics = SetOptimizationMetrics(
            objective=final_obj,
            relevance=final_metrics["relevance"],
            structural_coherence=final_metrics["structural_coherence"],
            coverage=final_metrics["coverage"],
            redundancy=final_metrics["redundancy"],
            dispersion=final_metrics["dispersion"],
            tokens_used=final_metrics["tokens_used"],
            blocks_selected=len(selected),
            marginal_gain_sequence=marginal_gains,
            marginal_gain_breakdown=marginal_gain_breakdown,
            weight_vector_used=weight_vector,
            base_weight_vector=weight_vector,
            effective_weight_vector=weight_vector,
            final_distinct_file_count=distinct_files,
        )
        return selected, metrics

    def _objective(self, metrics: dict[str, float], weights: SetObjectiveWeights) -> float:
        return (
            weights.relevance * metrics["relevance"]
            + weights.structural_coherence * metrics["structural_coherence"]
            + weights.coverage * metrics["coverage"]
            - weights.redundancy * metrics["redundancy"]
            - weights.dispersion * metrics["dispersion"]
        )

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
                "redundancy": 0.0,
                "dispersion": 0.0,
                "tokens_used": 0.0,
            }

        relevance = self._relevance(selected, relevance_map, max_candidates)
        structural_coherence = self._structural_coherence(selected)
        coverage = self._coverage(selected, concept_set, concept_hits)
        redundancy = self._redundancy(selected)
        dispersion = self._dispersion(selected)
        tokens_used = sum(self._estimate_tokens(c) for c in selected)

        return {
            "relevance": self._clamp01(relevance),
            "structural_coherence": self._clamp01(structural_coherence),
            "coverage": self._clamp01(coverage),
            "redundancy": self._clamp01(redundancy),
            "dispersion": self._clamp01(dispersion),
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

    def _dispersion(self, selected: list[Candidate]) -> float:
        """
        Concentration penalty (0..1): higher means more single-file dominance.

        Used as a penalty term in the objective:
        -dispersion_weight * concentration_penalty

        Definition:
        penalty = 1 - (distinct_files / selected_count)
        """
        if not selected:
            return 0.0
        selected_count = len(selected)
        distinct_files = len({c.file for c in selected if c.file})
        if selected_count <= 1 or distinct_files <= 0:
            return 0.0
        ratio = distinct_files / selected_count
        return self._clamp01(1.0 - ratio)

    def _avg_span_overlap(self, selected: list[Candidate]) -> float:
        overlaps = []
        for i, a in enumerate(selected):
            for b in selected[i + 1:]:
                overlaps.append(self._span_overlap_ratio(a, b))
        if not overlaps:
            return 0.0
        return sum(overlaps) / len(overlaps)

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
