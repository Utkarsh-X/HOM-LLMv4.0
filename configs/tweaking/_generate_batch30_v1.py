from pathlib import Path
import copy
import yaml


root = Path(r"d:\HOM-LLM(v2.0)")
base_path = (
    root
    / "tuning"
    / "resolved_configs"
    / "ccg_v2_ab_budget5200_weights_dynamic_budget.resolved.yaml"
)
out_dir = root / "configs" / "tweaking" / "ccg_resolved_batch30_v1"
out_dir.mkdir(parents=True, exist_ok=True)


with base_path.open("r", encoding="utf-8") as f:
    base = yaml.safe_load(f)


variants = [
    (
        "ccg30_01_baseline",
        {},
        "Resolved winning CCG config with all fallback defaults materialized.",
    ),
    (
        "ccg30_02_ret_precision_add2",
        {"retrieval": {"precision_recovery": {"max_additions": 2}}},
        "Reduce precision recovery additions below the resolved baseline.",
    ),
    (
        "ccg30_03_ret_precision_add4",
        {"retrieval": {"precision_recovery": {"max_additions": 4}}},
        "Increase precision recovery additions above the resolved baseline.",
    ),
    (
        "ccg30_04_ret_precision_scan6",
        {"retrieval": {"precision_recovery": {"scan_candidates": 6}}},
        "Narrow the precision recovery scan window.",
    ),
    (
        "ccg30_05_ret_precision_scan10",
        {"retrieval": {"precision_recovery": {"scan_candidates": 10}}},
        "Widen the precision recovery scan window.",
    ),
    (
        "ccg30_06_ret_precision_conf075",
        {"retrieval": {"precision_recovery": {"min_confidence": 0.75}}},
        "Loosen precision recovery confidence threshold.",
    ),
    (
        "ccg30_07_ret_precision_conf085",
        {"retrieval": {"precision_recovery": {"min_confidence": 0.85}}},
        "Tighten precision recovery confidence threshold.",
    ),
    (
        "ccg30_08_ret_coverage_add2",
        {"retrieval": {"coverage_recovery": {"max_additions": 2}}},
        "Reduce coverage recovery insertions.",
    ),
    (
        "ccg30_09_ret_coverage_add4",
        {"retrieval": {"coverage_recovery": {"max_additions": 4}}},
        "Increase coverage recovery insertions.",
    ),
    (
        "ccg30_10_ret_postmerge_40",
        {"retrieval": {"post_merge_candidates": 40}},
        "Shrink the post-merge candidate surface.",
    ),
    (
        "ccg30_11_ret_postmerge_60",
        {"retrieval": {"post_merge_candidates": 60}},
        "Expand the post-merge candidate surface.",
    ),
    (
        "ccg30_12_ctx_dynstep_300",
        {"context": {"dynamic_budget_step_tokens": 300}},
        "Use a smaller dynamic budget expansion step.",
    ),
    (
        "ccg30_13_ctx_dynstep_500",
        {"context": {"dynamic_budget_step_tokens": 500}},
        "Use a larger dynamic budget expansion step.",
    ),
    (
        "ccg30_14_ctx_dynexp_1",
        {"context": {"dynamic_budget_max_expansions": 1}},
        "Limit dynamic budget to a single expansion.",
    ),
    (
        "ccg30_15_ctx_dynexp_3",
        {"context": {"dynamic_budget_max_expansions": 3}},
        "Allow one more dynamic budget expansion than the resolved baseline.",
    ),
    (
        "ccg30_16_ctx_relgate_020",
        {"context": {"relevance_gate_threshold": 0.20}},
        "Loosen the relevance gate to admit weaker blocks.",
    ),
    (
        "ccg30_17_ctx_relgate_030",
        {"context": {"relevance_gate_threshold": 0.30}},
        "Tighten the relevance gate to reject weaker blocks.",
    ),
    (
        "ccg30_18_ctx_graph_015",
        {"context": {"submodular": {"w_rrf": 0.60, "w_graph": 0.15}}},
        "Reduce graph weight and return that mass to RRF.",
    ),
    (
        "ccg30_19_ctx_graph_025",
        {"context": {"submodular": {"w_rrf": 0.50, "w_graph": 0.25}}},
        "Increase graph weight and reduce RRF slightly.",
    ),
    (
        "ccg30_20_ctx_unresblocks_1",
        {"context": {"unresolved_evidence_injection_max_blocks": 1}},
        "Make unresolved evidence injection more conservative.",
    ),
    (
        "ccg30_21_ctx_unresblocks_3",
        {"context": {"unresolved_evidence_injection_max_blocks": 3}},
        "Make unresolved evidence injection more aggressive.",
    ),
    (
        "ccg30_22_rank_bm25rescue_10",
        {"ranking": {"reranker": {"bm25_rescue_top_k": 10}}},
        "Reduce the BM25 rescue set passed into reranking.",
    ),
    (
        "ccg30_23_rank_bm25rescue_20",
        {"ranking": {"reranker": {"bm25_rescue_top_k": 20}}},
        "Increase the BM25 rescue set passed into reranking.",
    ),
    (
        "ccg30_24_rank_topm_25",
        {"ranking": {"reranker": {"top_m": 25}}},
        "Rerank a smaller candidate set.",
    ),
    (
        "ccg30_25_rank_topm_45",
        {"ranking": {"reranker": {"top_m": 45}}},
        "Rerank a larger candidate set.",
    ),
    (
        "ccg30_26_rank_gate_margin_015",
        {"ranking": {"reranker": {"gating": {"threshold_margin": 0.15}}}},
        "Loosen reranker gating margin.",
    ),
    (
        "ccg30_27_rank_gate_margin_025",
        {"ranking": {"reranker": {"gating": {"threshold_margin": 0.25}}}},
        "Tighten reranker gating margin.",
    ),
    (
        "ccg30_28_combo_retrieval_breadth_high",
        {
            "retrieval": {
                "precision_recovery": {"max_additions": 4},
                "coverage_recovery": {"max_additions": 4},
                "post_merge_candidates": 60,
            }
        },
        "Expand retrieval breadth across precision recovery, coverage recovery, and post-merge candidates together.",
    ),
    (
        "ccg30_29_combo_context_conservative",
        {
            "context": {
                "dynamic_budget_max_expansions": 1,
                "relevance_gate_threshold": 0.30,
                "unresolved_evidence_injection_max_blocks": 1,
            }
        },
        "Conservative context regime with tighter gates and lower rescue allowance.",
    ),
    (
        "ccg30_30_combo_context_aggressive",
        {
            "context": {
                "dynamic_budget_max_expansions": 3,
                "relevance_gate_threshold": 0.20,
                "unresolved_evidence_injection_max_blocks": 3,
            }
        },
        "Aggressive context regime with broader expansion and stronger rescue allowance.",
    ),
]


def deep_merge(dst, src):
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            deep_merge(dst[key], value)
        else:
            dst[key] = copy.deepcopy(value)
    return dst


index = []
for name, overrides, rationale in variants:
    payload = copy.deepcopy(base)
    deep_merge(payload, overrides)
    path = out_dir / f"{name}.yaml"
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=False)
    index.append(
        {
            "name": name,
            "file": path.name,
            "rationale": rationale,
            "overrides": overrides,
        }
    )


index_payload = {
    "base_config": str(base_path.relative_to(root)).replace("\\", "/"),
    "variants": index,
}
with (out_dir / "variant_index.yaml").open("w", encoding="utf-8") as f:
    yaml.safe_dump(index_payload, f, sort_keys=False, allow_unicode=False)


lines = [
    "# Manual Runbook",
    "",
    "Base directory: `configs/tweaking/ccg_resolved_batch30_v1`",
    "",
    "Each batch gets:",
    "- 1 experiment run",
    "- 1 Gemini judge run",
    "- 1 Cerebras SDK judge run",
    "",
    "Rules:",
    "- Do not chain batches together.",
    "- Run one batch at a time.",
    "- If Gemini judge fails, rerun only the Gemini judge command for that batch.",
    "- If Cerebras judge fails, rerun only the Cerebras judge command for that batch.",
    "- If a partial judge output file exists, delete it first and rerun the same command.",
    "- Do not rerun `run_experiment.py` unless the responses file is missing or corrupted.",
    "",
]

for item in index:
    name = item["name"]
    cfg_rel = f"configs/tweaking/ccg_resolved_batch30_v1/{item['file']}"
    lines.extend(
        [
            f"## {name}",
            f"Rationale: {item['rationale']}",
            "",
            "```powershell",
            f"py eval/run_experiment.py --select 1-20 --config {cfg_rel} --run-name {name} --telemetry-print",
            f"py eval/run_judge.py --responses eval/runs/{name}/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/{name}/judge_results__gemini_manual.jsonl",
            f"py eval/run_judge.py --responses eval/runs/{name}/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/{name}/judge_results__cerebras_manual.jsonl",
            "```",
            "",
        ]
    )

(out_dir / "MANUAL_RUNBOOK.md").write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {len(index)} variants to {out_dir}")
