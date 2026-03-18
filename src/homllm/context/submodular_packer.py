"""Tier 3B: Submodular Context Packer.

Replaces greedy budget fill with marginal-gain density maximization.
Uses four utility components: normalized_rrf, novelty_gain, graph_gain, concept_gain.

Production constraints:
- Deterministic only (no stochastic sampling)
- No recursion
- Candidate count bounded <= 150
- O(n*k) complexity
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from homllm.context.interfaces import ScoredBlock

logger = logging.getLogger(__name__)

_FP_COMPARISON_EPS = 1e-12
_FP_ROUND_DECIMALS = 12
_EPSILON_GUARD_RRF_RATIO = 0.85
_UTILITY_GUARD_THRESHOLDS = {
    "rrf_min_share": 0.60,
    "novelty_max_share": 0.20,
    "graph_max_share": 0.10,
}


@dataclass
class PackerConfig:
    """Configuration for submodular context packer."""

    # Utility weights (must sum to ~1.0)
    w_rrf: float = 0.40
    w_novelty: float = 0.20
    w_graph: float = 0.20
    w_concept: float = 0.20

    # Budget
    max_tokens: int = 3600

    # Stopping
    min_density_epsilon: float = 0.001
    # Experimental noise guard (off by default)
    noise_guard_enabled: bool = False
    noise_guard_min_file_ratio: float = 0.60
    noise_guard_rrf_ratio_threshold: float = 0.85

    # Tier 3C: Novelty scaling mode
    # - "none": fixed novelty weight
    # - "file_concentration": novelty weight *= (1 - top_file_ratio)
    novelty_scaling: str = "none"

    # Toggle
    enabled: bool = False


@dataclass
class PackerResult:
    """Result of submodular packing."""

    selected: list[ScoredBlock]
    telemetry: dict


def _normalize_fp(value: float) -> float:
    """Normalize float precision for stable comparisons across runs/platforms."""
    return round(float(value), _FP_ROUND_DECIMALS)


def _estimate_tokens(content: str, tokenizer: object | None = None) -> int:
    """Token count: uses real tokenizer if available, else chars / 4."""
    if tokenizer is not None:
        try:
            return max(1, len(tokenizer.encode(content)))
        except Exception:
            pass
    return max(1, len(content) // 4)


def _extract_concepts(query: str) -> set[str]:
    """Extract simple concept tokens from query for concept coverage."""
    # Split on non-alphanumeric, lowercase, filter short tokens
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", query.lower())
    return {t for t in tokens if len(t) >= 3}


def _block_concepts(block: ScoredBlock) -> set[str]:
    """Extract concept tokens from a block's content."""
    content = block.block.content if block.block.content else ""
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", content.lower())
    return {t for t in tokens if len(t) >= 3}


def submodular_pack(
    candidates: list[ScoredBlock],
    query: str,
    config: PackerConfig,
    graph_edges: Optional[dict[str, set[str]]] = None,
    tokenizer: object | None = None,
) -> PackerResult:
    """Greedy density-maximized submodular context packing.

    For each candidate c given selected set S:
        U(c|S) = w1 * normalized_rrf + w2 * novelty_gain + w3 * graph_gain + w4 * concept_gain
        density = U(c|S) / token_count(c)
    
    Select argmax density until budget exhausted or density < epsilon.

    Args:
        candidates: Scored blocks sorted by final_score descending.
        query: Original query string.
        config: Packer configuration.
        graph_edges: Optional adjacency dict {entity_id: {neighbor_ids}}.
    
    Returns:
        PackerResult with selected blocks and telemetry.
    """
    if not candidates:
        return PackerResult(selected=[], telemetry={"initial_count": 0})

    n = len(candidates)
    max_tokens = config.max_tokens

    # Pre-compute score bounds for normalization
    scores = [c.final_score for c in candidates]
    score_min = min(scores)
    score_max = max(scores)
    score_range = score_max - score_min if score_max > score_min else 1.0

    # Pre-compute token estimates
    token_counts = [_estimate_tokens(c.block.content or "", tokenizer) for c in candidates]

    # Pre-compute concept sets
    query_concepts = _extract_concepts(query)
    block_concept_sets = [_block_concepts(c) for c in candidates]

    # Pre-compute file sets for novelty (file-level diversity)
    block_files = [c.block.file for c in candidates]

    # Graph: build set of covered edges for graph_gain
    graph_edges = graph_edges or {}

    # State tracking
    selected: list[ScoredBlock] = []
    selected_indices: set[int] = set()
    used_tokens = 0
    covered_files: set[str] = set()
    selected_file_counts: dict[str, int] = {}
    covered_concepts: set[str] = set()
    covered_graph_edges: set[tuple[str, str]] = set()
    marginal_gains: list[float] = []
    marginal_densities: list[float] = []
    novelty_penalties: list[float] = []
    selection_trace: list[dict] = []
    stop_reason = "budget_exhausted"
    density_at_stop = 0.0
    epsilon_stop_step: Optional[int] = None
    epsilon_guard_triggered = False
    epsilon_guard_trigger_count = 0
    epsilon_guard_last_remaining_rrf_ratio = 0.0
    noise_guard_triggered = False
    noise_guard_trigger_count = 0

    total_rrf_component = 0.0
    total_novelty_component = 0.0
    total_graph_component = 0.0
    total_concept_component = 0.0

    # All graph edges relevant to this query's candidates
    candidate_entity_ids = set()
    for c in candidates:
        if hasattr(c.block, "symbol_id") and c.block.symbol_id:
            candidate_entity_ids.add(c.block.symbol_id)

    relevant_edges: set[tuple[str, str]] = set()
    for eid in candidate_entity_ids:
        for dst in graph_edges.get(eid, set()):
            relevant_edges.add((eid, dst))
    total_relevant_edges = max(1, len(relevant_edges))

    # Greedy selection loop
    while used_tokens < max_tokens:
        best_idx = -1
        best_density = -1.0
        best_tie_key: tuple[float, int, str] | None = None
        best_utility = 0.0
        best_rrf_component = 0.0
        best_novelty_component = 0.0
        best_graph_component = 0.0
        best_concept_component = 0.0
        best_normalized_rrf = 0.0
        best_novelty_gain = 0.0
        best_graph_gain = 0.0
        best_concept_gain = 0.0
        best_novelty_penalty = 0.0
        best_novelty_weight_effective = 0.0
        best_top_file_ratio = 0.0
        best_new_concepts: set[str] = set()
        best_new_graph_edges: set[tuple[str, str]] = set()
        fit_indices: list[int] = []

        for i in range(n):
            if i in selected_indices:
                continue

            # Skip if doesn't fit
            if used_tokens + token_counts[i] > max_tokens:
                continue
            fit_indices.append(i)

            # Component 1: normalized RRF score
            normalized_rrf = (scores[i] - score_min) / score_range

            # Component 2: novelty gain (file diversity)
            file_path = block_files[i]
            novelty_gain = 1.0 if file_path not in covered_files else 0.2
            novelty_penalty = 1.0 - novelty_gain

            if selected:
                top_file_ratio = max(selected_file_counts.values()) / len(selected)
            else:
                top_file_ratio = 0.0

            novelty_weight_effective = config.w_novelty
            if config.novelty_scaling == "file_concentration":
                novelty_weight_effective = config.w_novelty * (1.0 - top_file_ratio)

            # Component 3: graph gain (new structural edges)
            graph_gain = 0.0
            new_graph_edges: set[tuple[str, str]] = set()
            block_symbol_id = None
            if hasattr(candidates[i].block, "symbol_id"):
                block_symbol_id = candidates[i].block.symbol_id
            if block_symbol_id and block_symbol_id in graph_edges:
                block_edges = {(block_symbol_id, dst) for dst in graph_edges[block_symbol_id]}
                new_graph_edges = block_edges - covered_graph_edges
                graph_gain = len(new_graph_edges) / total_relevant_edges
            
            # Component 4: concept gain (new query concepts covered)
            new_concepts: set[str] = set()
            if query_concepts:
                new_concepts = (block_concept_sets[i] & query_concepts) - covered_concepts
                concept_gain = len(new_concepts) / len(query_concepts)
            else:
                concept_gain = 0.0

            rrf_component = config.w_rrf * normalized_rrf
            novelty_component = novelty_weight_effective * novelty_gain
            graph_component = config.w_graph * graph_gain
            concept_component = config.w_concept * concept_gain

            # Marginal utility
            utility = rrf_component + novelty_component + graph_component + concept_component

            # Density = utility per token
            density = _normalize_fp(utility / token_counts[i])
            tie_key = (-utility, i, str(candidates[i].block.block_id))

            is_better = density > (best_density + _FP_COMPARISON_EPS)
            if not is_better and abs(density - best_density) <= _FP_COMPARISON_EPS:
                if best_tie_key is None or tie_key < best_tie_key:
                    is_better = True

            if is_better:
                best_density = density
                best_tie_key = tie_key
                best_utility = utility
                best_idx = i
                best_rrf_component = rrf_component
                best_novelty_component = novelty_component
                best_graph_component = graph_component
                best_concept_component = concept_component
                best_normalized_rrf = normalized_rrf
                best_novelty_gain = novelty_gain
                best_graph_gain = graph_gain
                best_concept_gain = concept_gain
                best_novelty_penalty = novelty_penalty
                best_novelty_weight_effective = novelty_weight_effective
                best_top_file_ratio = top_file_ratio
                best_new_concepts = new_concepts
                best_new_graph_edges = new_graph_edges

        # Check stop conditions
        if best_idx < 0:
            stop_reason = "no_candidate_fits"
            break
        remaining_max_rrf_raw = max((scores[j] for j in fit_indices), default=0.0)
        epsilon_guard_last_remaining_rrf_ratio = (
            (remaining_max_rrf_raw / score_max) if score_max > 0 else 0.0
        )

        epsilon_guard_forced_this_step = False
        noise_guard_forced_this_step = False
        if best_density + _FP_COMPARISON_EPS < _normalize_fp(config.min_density_epsilon):
            if (
                config.noise_guard_enabled
                and best_concept_gain <= 0.0
                and best_graph_gain <= 0.0
                and best_top_file_ratio >= config.noise_guard_min_file_ratio
                and epsilon_guard_last_remaining_rrf_ratio < config.noise_guard_rrf_ratio_threshold
            ):
                noise_guard_forced_this_step = True
                noise_guard_triggered = True
                noise_guard_trigger_count += 1
                stop_reason = "noise_guard"
                epsilon_stop_step = len(selected) + 1
                density_at_stop = best_density
                break
            if epsilon_guard_last_remaining_rrf_ratio >= _EPSILON_GUARD_RRF_RATIO:
                epsilon_guard_forced_this_step = True
                epsilon_guard_triggered = True
                epsilon_guard_trigger_count += 1
                logger.info(
                    "[SUBMODULAR_EPSILON_GUARD] bypassed epsilon stop: density=%.12f epsilon=%.12f remaining_rrf_ratio=%.3f",
                    best_density,
                    config.min_density_epsilon,
                    epsilon_guard_last_remaining_rrf_ratio,
                )
            else:
                stop_reason = "epsilon"
                epsilon_stop_step = len(selected) + 1
                density_at_stop = best_density
                break

        # Select best
        selected.append(candidates[best_idx])
        selected_indices.add(best_idx)
        used_tokens += token_counts[best_idx]
        marginal_gains.append(best_utility)
        marginal_densities.append(best_density)
        novelty_penalties.append(best_novelty_penalty)
        total_rrf_component += best_rrf_component
        total_novelty_component += best_novelty_component
        total_graph_component += best_graph_component
        total_concept_component += best_concept_component
        density_at_stop = best_density
        selection_trace.append(
            {
                "step": len(selected),
                "block_id": candidates[best_idx].block.block_id,
                "file": candidates[best_idx].block.file,
                "rank_position": best_idx + 1,
                "token_count": token_counts[best_idx],
                "normalized_rrf": round(best_normalized_rrf, 6),
                "novelty_gain": round(best_novelty_gain, 6),
                "novelty_penalty": round(best_novelty_penalty, 6),
                "novelty_weight_effective": round(best_novelty_weight_effective, 6),
                "top_file_ratio": round(best_top_file_ratio, 6),
                "graph_gain": round(best_graph_gain, 6),
                "concept_gain": round(best_concept_gain, 6),
                "rrf_component": round(best_rrf_component, 6),
                "novelty_component": round(best_novelty_component, 6),
                "graph_component": round(best_graph_component, 6),
                "concept_component": round(best_concept_component, 6),
                "marginal_utility": round(best_utility, 6),
                "marginal_density": round(best_density, 6),
                "epsilon_guard_forced": epsilon_guard_forced_this_step,
                "noise_guard_forced": noise_guard_forced_this_step,
            }
        )

        # Update coverage state
        selected_file = block_files[best_idx]
        covered_files.add(selected_file)
        selected_file_counts[selected_file] = selected_file_counts.get(selected_file, 0) + 1
        covered_concepts.update(best_new_concepts)
        covered_graph_edges.update(best_new_graph_edges)

    # Build telemetry
    concept_coverage = len(covered_concepts) / len(query_concepts) if query_concepts else 0.0
    graph_coverage = len(covered_graph_edges) / total_relevant_edges if total_relevant_edges else 0.0
    remaining_unused_tokens = max_tokens - used_tokens
    token_utilization = used_tokens / max_tokens if max_tokens > 0 else 0.0
    average_marginal_gain = (
        sum(marginal_gains) / len(marginal_gains) if marginal_gains else 0.0
    )
    final_marginal_gain_at_stop = marginal_gains[-1] if marginal_gains else 0.0

    total_utility_component = (
        total_rrf_component
        + total_novelty_component
        + total_graph_component
        + total_concept_component
    )
    rrf_dominance_ratio = (
        total_rrf_component / total_utility_component
        if total_utility_component > 0
        else 0.0
    )
    utility_mass_shares = (
        {
            "rrf": round(total_rrf_component / total_utility_component, 6),
            "novelty": round(total_novelty_component / total_utility_component, 6),
            "graph": round(total_graph_component / total_utility_component, 6),
            "concept": round(total_concept_component / total_utility_component, 6),
        }
        if total_utility_component > 0
        else {"rrf": 0.0, "novelty": 0.0, "graph": 0.0, "concept": 0.0}
    )
    utility_violations: list[str] = []
    if utility_mass_shares["rrf"] < _UTILITY_GUARD_THRESHOLDS["rrf_min_share"]:
        utility_violations.append("rrf_share_below_min")
    if utility_mass_shares["novelty"] > _UTILITY_GUARD_THRESHOLDS["novelty_max_share"]:
        utility_violations.append("novelty_share_above_max")
    if utility_mass_shares["graph"] > _UTILITY_GUARD_THRESHOLDS["graph_max_share"]:
        utility_violations.append("graph_share_above_max")
    utility_guard_passed = not utility_violations
    if not utility_guard_passed:
        logger.warning(
            "[SUBMODULAR_UTILITY_GUARD] threshold violation: violations=%s shares=%s",
            ",".join(utility_violations),
            utility_mass_shares,
        )

    novelty_penalty_distribution = {
        "count": len(novelty_penalties),
        "mean": round(sum(novelty_penalties) / len(novelty_penalties), 6)
        if novelty_penalties
        else 0.0,
        "min": round(min(novelty_penalties), 6) if novelty_penalties else 0.0,
        "max": round(max(novelty_penalties), 6) if novelty_penalties else 0.0,
        "values_first20": [round(v, 6) for v in novelty_penalties[:20]],
    }

    telemetry = {
        "total_candidates_before_packing": n,
        "initial_candidate_count": n,
        "selected_blocks": len(selected),
        "final_selected_count": len(selected),
        "total_tokens_used": used_tokens,
        "max_tokens_budget": max_tokens,
        "token_utilization": round(token_utilization, 6),
        "unused_tokens": remaining_unused_tokens,
        "remaining_unused_tokens": remaining_unused_tokens,
        "concept_coverage": round(concept_coverage, 3),
        "concept_coverage_delta": round(concept_coverage, 3),
        "graph_edge_coverage": round(graph_coverage, 3),
        "files_covered": len(covered_files),
        "marginal_gain_curve": [round(g, 4) for g in marginal_gains[:20]],
        "marginal_density_curve": [round(d, 6) for d in marginal_densities],
        "marginal_density_curve_first20": [round(d, 6) for d in marginal_densities[:20]],
        "average_marginal_gain": round(average_marginal_gain, 6),
        "final_marginal_gain_at_stop": round(final_marginal_gain_at_stop, 6),
        "min_density_at_stop": round(density_at_stop, 6),
        "density_at_stop": round(density_at_stop, 6),
        "stop_reason": stop_reason,
        "epsilon_stop_step": epsilon_stop_step,
        "epsilon_guard": {
            "enabled": True,
            "rrf_ratio_threshold": _EPSILON_GUARD_RRF_RATIO,
            "triggered": epsilon_guard_triggered,
            "trigger_count": epsilon_guard_trigger_count,
            "remaining_max_rrf_ratio_at_stop": round(epsilon_guard_last_remaining_rrf_ratio, 6),
        },
        "noise_guard": {
            "enabled": config.noise_guard_enabled,
            "min_file_ratio": config.noise_guard_min_file_ratio,
            "rrf_ratio_threshold": config.noise_guard_rrf_ratio_threshold,
            "triggered": noise_guard_triggered,
            "trigger_count": noise_guard_trigger_count,
            "remaining_max_rrf_ratio_at_stop": round(epsilon_guard_last_remaining_rrf_ratio, 6),
        },
        "novelty_penalty_distribution": novelty_penalty_distribution,
        "rrf_dominance_ratio": round(rrf_dominance_ratio, 6),
        "utility_mass_shares": utility_mass_shares,
        "utility_sanity_guard": {
            "thresholds": _UTILITY_GUARD_THRESHOLDS,
            "passed": utility_guard_passed,
            "violations": utility_violations,
            "auto_adjustment_applied": False,
        },
        "selection_trace": selection_trace,
        "utility_component_totals": {
            "rrf_component": round(total_rrf_component, 6),
            "novelty_component": round(total_novelty_component, 6),
            "graph_component": round(total_graph_component, 6),
            "concept_component": round(total_concept_component, 6),
        },
        "weight_vector": {
            "w_rrf": config.w_rrf,
            "w_novelty": config.w_novelty,
            "w_graph": config.w_graph,
            "w_concept": config.w_concept,
        },
        "min_density_epsilon": config.min_density_epsilon,
        "novelty_scaling": config.novelty_scaling,
        "floating_point_normalization": {
            "comparison_epsilon": _FP_COMPARISON_EPS,
            "round_decimals": _FP_ROUND_DECIMALS,
        },
    }

    logger.info(
        "[SUBMODULAR_PACK] candidates=%d selected=%d tokens=%d/%d concept_cov=%.2f files=%d",
        n,
        len(selected),
        used_tokens,
        max_tokens,
        concept_coverage,
        len(covered_files),
    )

    return PackerResult(selected=selected, telemetry=telemetry)
