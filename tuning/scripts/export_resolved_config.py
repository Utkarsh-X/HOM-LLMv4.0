#!/usr/bin/env python3
"""Export the effective runtime config after YAML + fallback defaults are resolved."""

from __future__ import annotations

import argparse
import copy
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from homllm.claim_coverage.interfaces import ClaimCoverageConfig
from homllm.common.config import Config
from homllm.intelligence.fixer_config import get_abrm_config, get_fixer_config


def _normalize(value: Any) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a mapping at root of {path}")
    return payload


def _materialize_indexer(raw: dict[str, Any], config: Config) -> dict[str, Any]:
    idx = config.get_indexer_config()
    section = copy.deepcopy(_normalize(raw.get("indexer", {})))
    section["languages"] = list(idx.languages)
    section["ignore_patterns"] = list(idx.ignore_patterns)
    section["chunk_max_lines"] = idx.chunk_max_lines
    section["vector_indexing_enabled"] = idx.vector_indexing_enabled
    section["embedding_model"] = idx.embedding_model
    section["embedding_dimension"] = idx.embedding_dimension
    section["embedding_max_tokens"] = idx.embedding_max_tokens
    section["embedding_device"] = idx.embedding_device
    section["entity_centric_indexing_enabled"] = idx.entity_centric_indexing_enabled
    section["type_alias_extraction_enabled"] = idx.type_alias_extraction_enabled
    section["storage"] = _normalize(idx.storage)
    section["entity_confidence"] = _normalize(idx.entity_confidence)
    section["hierarchical_chunking"] = _normalize(idx.hierarchical_chunking)
    return section


def _materialize_retrieval(raw: dict[str, Any], config: Config) -> dict[str, Any]:
    ret = config.get_retrieval_config()
    section = copy.deepcopy(_normalize(raw.get("retrieval", {})))

    section.setdefault("bm25", {})
    section["bm25"]["top_k"] = ret.bm25_top_k
    section["bm25"].setdefault("engine", "tantivy")

    section.setdefault("vector", {})
    section["vector"]["top_k"] = ret.vector_top_k
    section["vector"]["calibration_mode"] = ret.vector_calibration_mode
    section["vector"].setdefault("engine", "lancedb")

    section.setdefault("hybrid", {})
    section["hybrid"]["method"] = ret.hybrid_method
    section["hybrid"]["rrf_k"] = ret.rrf_k
    section["hybrid"]["bm25_weight"] = ret.bm25_weight
    section["hybrid"]["vector_weight"] = ret.vector_weight

    section["plan_b_enabled"] = ret.plan_b_enabled
    section["post_merge_candidates"] = ret.post_merge_candidates
    section["parallel_search"] = {"enabled": ret.parallel_search_enabled}
    section["static_ceiling_experiment"] = {
        "enabled": ret.static_ceiling_experiment_enabled,
        "branch_multiplier": ret.static_ceiling_branch_multiplier,
        "post_merge_multiplier": ret.static_ceiling_post_merge_multiplier,
        "output_multiplier": ret.static_ceiling_output_multiplier,
    }
    section["precision_recovery"] = {
        "enabled": ret.precision_recovery_enabled,
        "max_additions": ret.precision_recovery_max_additions,
        "max_ratio": ret.precision_recovery_max_ratio,
        "scan_candidates": ret.precision_recovery_scan_candidates,
        "identifier_limit": ret.precision_recovery_identifier_limit,
        "bm25_top_k": ret.precision_recovery_bm25_top_k,
        "vector_top_k": ret.precision_recovery_vector_top_k,
        "min_confidence": ret.precision_recovery_min_confidence,
    }
    section["query_expansion"] = {
        "enabled": ret.query_expansion_enabled,
        "max_terms": ret.query_expansion_max_terms,
        "min_token_length": ret.query_expansion_min_token_length,
        "synonyms": _normalize(ret.query_expansion_synonyms),
    }
    section["expansion"] = {
        "enabled": ret.expansion_enabled,
        "max_additions": ret.expansion_max_additions,
        "min_similarity": ret.expansion_min_similarity,
    }
    section["adaptive_seed"] = {
        "enabled": ret.adaptive_seed_enabled,
        "min_k": ret.adaptive_seed_min_k,
        "max_k": ret.adaptive_seed_max_k,
        "drop_threshold": ret.adaptive_seed_drop_threshold,
    }
    section["diversity_mmr"] = {
        "enabled": ret.diversity_mmr_enabled,
        "lambda": ret.mmr_lambda,
        "similarity_threshold": ret.mmr_similarity_threshold,
    }
    section["granularity_boost"] = {
        "enabled": ret.granularity_boost_enabled,
        **_normalize(ret.granularity_boost_table),
    }
    section["graph_stitch"] = {
        "enabled": ret.graph_stitch_enabled,
        "max_depth": ret.graph_stitch_max_depth,
        "max_additions": ret.graph_stitch_max_additions,
        "min_confidence": ret.graph_stitch_min_confidence,
        "relation_priority": _normalize(ret.graph_stitch_relation_priority),
        "graph_cache_enabled": ret.graph_cache_enabled,
        "graph_stitch_beam_high": ret.graph_stitch_beam_high,
        "graph_stitch_beam_low": ret.graph_stitch_beam_low,
    }
    section["budget"] = {"enabled": ret.budget_aware_selection}
    section["granularity_mixing"] = {
        "enabled": ret.granularity_mixing_enabled,
        "profiles": _normalize(ret.granularity_mixing_profiles),
    }
    section["hierarchical_dedup"] = {"enabled": ret.hierarchical_dedup_enabled}
    section["coverage_recovery"] = {
        "enabled": ret.coverage_recovery_enabled,
        "max_additions": ret.coverage_recovery_max_additions,
        "max_ratio": ret.coverage_recovery_max_ratio,
        "bm25_top_k": ret.coverage_recovery_bm25_top_k,
    }
    return section


def _materialize_ranking(raw: dict[str, Any], config: Config) -> dict[str, Any]:
    rank = config.get_ranking_config()
    section = copy.deepcopy(_normalize(raw.get("ranking", {})))
    section["concentration_top_k"] = rank.concentration_top_k
    section["graph_proximity"] = {
        "max_depth": rank.graph_max_depth,
        "anchor_k": rank.graph_anchor_k,
    }
    section["dedup"] = {"file_entropy_threshold": rank.dedup_file_entropy_threshold}
    section["phase2"] = {
        "enabled": rank.phase2_enabled,
        "adaptive_weights_enabled": rank.adaptive_weights_enabled,
    }
    section["two_pass"] = {
        "enabled": rank.two_pass_enabled,
        "seed_k": rank.two_pass_seed_k,
        "max_depth": rank.two_pass_max_depth,
        "decay": rank.two_pass_decay,
    }
    section["mmr_selection"] = {
        "enabled": rank.mmr_enabled,
        "top_n": rank.mmr_top_n,
        "lambda": rank.mmr_lambda,
    }
    section["set_optimization"] = {
        "enabled": rank.set_opt_enabled,
        "token_budget": rank.set_opt_token_budget,
        "max_rounds": rank.set_opt_max_rounds,
        "w_relevance": rank.set_opt_w_relevance,
        "w_structural": rank.set_opt_w_structural,
        "w_coverage": rank.set_opt_w_coverage,
        "w_redundancy": rank.set_opt_w_redundancy,
        "w_dispersion": rank.set_opt_w_dispersion,
    }
    section["reranker"] = {
        "enabled": rank.reranker_enabled,
        "model": rank.reranker_model,
        "device": rank.reranker_device,
        "top_m": rank.reranker_top_m,
        "bm25_rescue_top_k": rank.reranker_bm25_rescue_top_k,
        "gating": {
            "enabled": rank.reranker_gating_enabled,
            "threshold_margin": rank.reranker_margin_threshold,
            "threshold_entropy": rank.reranker_entropy_threshold,
            "threshold_disagreement": rank.reranker_disagreement_threshold,
            "top_k": rank.reranker_gating_top_k,
            "min_candidates": rank.reranker_gating_min_candidates,
        },
    }
    section["geometry"] = {
        "rerank_alpha": rank.rerank_alpha,
        "struct_gamma": rank.struct_gamma,
    }
    section["weights"] = {
        "w_base": rank.w_base,
        "w_rerank": rank.w_rerank,
        "w_struct": rank.w_struct,
        "w_bm25": rank.w_bm25,
        "w_dense": rank.w_dense,
        "w_name": rank.w_name,
        "struct": {
            "entrypoint_bonus": rank.struct_entrypoint_bonus,
            "decorator_bonus": rank.struct_decorator_bonus,
            "callgraph_bonus": rank.struct_callgraph_bonus,
            "bonus_cap": rank.struct_bonus_cap,
        },
    }
    section["broad_system_bias"] = {
        "enabled": rank.broad_system_bias_enabled,
        "positive_weight": rank.w_broad_system_positive,
        "negative_weight": rank.w_broad_system_negative,
    }
    return section


def _materialize_context(raw: dict[str, Any], config: Config) -> dict[str, Any]:
    ctx = config.get_context_config()
    section = copy.deepcopy(_normalize(raw.get("context", {})))
    section["max_tokens"] = ctx.max_tokens
    section["budget_mode"] = ctx.budget_mode
    section["summarization_enabled"] = ctx.summarization_enabled
    section["ordering"] = ctx.ordering
    section["structural_priority_multiplier"] = ctx.structural_priority_multiplier
    section["generation_reserve_tokens"] = ctx.generation_reserve_tokens
    section["scoring_weights"] = {
        "w_semantic": ctx.w_semantic,
        "w_name": ctx.w_name,
        "w_structural": ctx.w_structural,
        "w_novelty": ctx.w_novelty,
        "w_coherence": ctx.w_coherence,
    }
    section["structural_priority_entrypoint_bonus"] = ctx.structural_priority_entrypoint_bonus
    section["structural_priority_decorator_bonus"] = ctx.structural_priority_decorator_bonus
    section["structural_priority_callgraph_bonus"] = ctx.structural_priority_callgraph_bonus
    section["structural_priority_cap"] = ctx.structural_priority_cap
    section["coherence_same_file_bonus"] = ctx.coherence_same_file_bonus
    section["coherence_different_file_bonus"] = ctx.coherence_different_file_bonus
    section["ranking_surface_lock_enabled"] = ctx.ranking_surface_lock_enabled
    section["coherence_enabled"] = ctx.coherence_enabled
    section["coherence_max_contribution"] = ctx.coherence_max_contribution
    section["coherence_protect_top_n"] = ctx.coherence_protect_top_n
    section["coherence_proximity_lines"] = ctx.coherence_proximity_lines
    section["coherence_synergy_threshold"] = ctx.coherence_synergy_threshold
    section["coherence_dispersion_threshold"] = ctx.coherence_dispersion_threshold
    section["coherence_callgraph_bonus"] = ctx.coherence_callgraph_bonus
    section["submodular_packer_enabled"] = ctx.submodular_packer_enabled
    section["submodular"] = {
        "w_rrf": ctx.submodular_w_rrf,
        "w_novelty": ctx.submodular_w_novelty,
        "w_graph": ctx.submodular_w_graph,
        "w_concept": ctx.submodular_w_concept,
        "min_density_epsilon": ctx.submodular_min_density_epsilon,
        "novelty_scaling": ctx.submodular_novelty_scaling,
        "noise_guard_enabled": ctx.submodular_noise_guard_enabled,
        "noise_guard_min_file_ratio": ctx.submodular_noise_guard_min_file_ratio,
        "noise_guard_rrf_ratio_threshold": ctx.submodular_noise_guard_rrf_ratio_threshold,
    }
    section["dynamic_budget_enabled"] = ctx.dynamic_budget_enabled
    section["dynamic_budget_trigger_used_pct"] = ctx.dynamic_budget_trigger_used_pct
    section["dynamic_budget_min_budget_limited_tokens"] = ctx.dynamic_budget_min_budget_limited_tokens
    section["dynamic_budget_safety_margin_tokens"] = ctx.dynamic_budget_safety_margin_tokens
    section["dynamic_budget_step_tokens"] = ctx.dynamic_budget_step_tokens
    section["dynamic_budget_max_expansions"] = ctx.dynamic_budget_max_expansions
    section["dynamic_budget_max_extra_tokens"] = ctx.dynamic_budget_max_extra_tokens
    section["dynamic_budget_tail_density_ratio_trigger"] = ctx.dynamic_budget_tail_density_ratio_trigger
    section["relevance_gate_enabled"] = ctx.relevance_gate_enabled
    section["relevance_gate_threshold"] = ctx.relevance_gate_threshold
    section["precision_filter_enabled"] = ctx.precision_filter_enabled
    section["precision_filter_query_identifier_min"] = ctx.precision_filter_query_identifier_min
    section["precision_filter_low_score_threshold"] = ctx.precision_filter_low_score_threshold
    section["precision_filter_min_kept_blocks"] = ctx.precision_filter_min_kept_blocks
    section["sparse_backfill_enabled"] = ctx.sparse_backfill_enabled
    section["sparse_backfill_min_utilization"] = ctx.sparse_backfill_min_utilization
    section["sparse_backfill_min_blocks"] = ctx.sparse_backfill_min_blocks
    section["sparse_backfill_max_additional_blocks"] = ctx.sparse_backfill_max_additional_blocks
    section["claim_gain_swap_enabled"] = ctx.claim_gain_swap_enabled
    section["claim_gain_swap_score_epsilon"] = ctx.claim_gain_swap_score_epsilon
    section["claim_gain_swap_max_swaps"] = ctx.claim_gain_swap_max_swaps
    section["claim_gain_swap_min_relevance_floor"] = ctx.claim_gain_swap_min_relevance_floor
    section["unresolved_evidence_injection_enabled"] = ctx.unresolved_evidence_injection_enabled
    section["unresolved_evidence_injection_max_blocks"] = ctx.unresolved_evidence_injection_max_blocks
    section["unresolved_evidence_injection_min_claim_gain"] = ctx.unresolved_evidence_injection_min_claim_gain
    section["unresolved_evidence_injection_relevance_floor"] = ctx.unresolved_evidence_injection_relevance_floor
    section["unresolved_evidence_injection_max_token_share"] = ctx.unresolved_evidence_injection_max_token_share
    section["unresolved_evidence_injection_replace_from_tail"] = ctx.unresolved_evidence_injection_replace_from_tail
    section["escape_hatch_enabled"] = ctx.escape_hatch_enabled
    return section


def _materialize_intelligence(raw: dict[str, Any], config: Config) -> dict[str, Any]:
    intelligence_cfg = config.get_intelligence_config()
    section = copy.deepcopy(_normalize(raw.get("intelligence", {})))
    section["enabled"] = intelligence_cfg.enabled
    section["level1_enabled"] = intelligence_cfg.level1_enabled
    section["level2_enabled"] = intelligence_cfg.level2_enabled
    section["level3_enabled"] = intelligence_cfg.level3_enabled

    fixer_cfg = get_fixer_config(config)
    section["mechanical_fixer_enabled"] = fixer_cfg.enabled
    section["action_priority"] = list(fixer_cfg.action_priority)
    section["thresholds"] = _normalize(fixer_cfg.thresholds)
    section["caps"] = _normalize(fixer_cfg.caps)

    abrm_cfg = get_abrm_config(config)
    section["abrm_enabled"] = abrm_cfg.enabled
    section["abrm_disable_on_cold_start"] = abrm_cfg.disable_on_cold_start
    section["p2_budget_increase_pct"] = float(section.get("p2_budget_increase_pct", 40.0))

    claim_cfg_raw = section.get("claim_coverage", {}) if isinstance(section.get("claim_coverage"), dict) else {}
    claim_cfg = ClaimCoverageConfig(
        enabled=claim_cfg_raw.get("enabled", False),
        required_coverage_threshold=claim_cfg_raw.get("required_coverage_threshold", 0.70),
        claim_cover_threshold=claim_cfg_raw.get("claim_cover_threshold", 0.55),
        soft_recovery_enabled=claim_cfg_raw.get("soft_recovery_enabled", True),
        max_recovery_passes=claim_cfg_raw.get("max_recovery_passes", 1),
        max_required_claims=claim_cfg_raw.get("max_required_claims", 8),
        recovery_top_k=claim_cfg_raw.get("recovery_top_k", 20),
        debug=claim_cfg_raw.get("debug", False),
        scoring_weights=claim_cfg_raw.get(
            "scoring_weights",
            {
                "lexical_anchor_match": 0.5,
                "symbol_match": 0.3,
                "structural_proximity": 0.2,
            },
        ),
    )
    section["claim_coverage"] = _normalize(claim_cfg)
    section["claim_coverage"]["prompt_contract_enabled"] = claim_cfg_raw.get("prompt_contract_enabled", False)
    return section


def _materialize_generation(raw: dict[str, Any], config: Config) -> dict[str, Any]:
    gen = config.get_generation_config()
    section = copy.deepcopy(_normalize(raw.get("generation", {})))
    section["default_provider"] = gen.default_provider
    section["default_model"] = gen.default_model
    section["temperature"] = gen.default_temperature
    section["max_output_tokens"] = gen.default_max_output_tokens
    section["default_template"] = gen.default_template
    return section


def _materialize_evaluation(raw: dict[str, Any]) -> dict[str, Any]:
    section = copy.deepcopy(_normalize(raw.get("evaluation", {})))
    section["cqi_hard_gate_enabled"] = bool(section.get("cqi_hard_gate_enabled", False))
    return section


def build_resolved_config(config_path: Path) -> dict[str, Any]:
    raw = _load_yaml(config_path)
    config = Config.from_file(config_path)
    return {
        "indexer": _materialize_indexer(raw, config),
        "retrieval": _materialize_retrieval(raw, config),
        "ranking": _materialize_ranking(raw, config),
        "context": _materialize_context(raw, config),
        "intelligence": _materialize_intelligence(raw, config),
        "generation": _materialize_generation(raw, config),
        "evaluation": _materialize_evaluation(raw),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export resolved HOM-LLM runtime config.")
    parser.add_argument("--config", type=Path, required=True, help="Source YAML config path.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output YAML path (default: tuning/resolved_configs/<stem>.resolved.yaml).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = (ROOT / args.config).resolve() if not args.config.is_absolute() else args.config.resolve()
    output_path = args.output
    if output_path is None:
        output_path = ROOT / "tuning" / "resolved_configs" / f"{config_path.stem}.resolved.yaml"
    elif not output_path.is_absolute():
        output_path = (ROOT / output_path).resolve()

    resolved = build_resolved_config(config_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(resolved, handle, sort_keys=False, allow_unicode=False)

    print(f"Resolved config written to: {output_path}")


if __name__ == "__main__":
    main()
