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
out_dir = root / "configs" / "tweaking" / "ccg_stage2_finetuning_v1"
out_dir.mkdir(parents=True, exist_ok=True)


with base_path.open("r", encoding="utf-8") as f:
    base = yaml.safe_load(f)


variants = [
    (
        "ccg15v2_01_baseline",
        {},
        "Resolved winning CCG config with all fallback defaults materialized.",
    ),
    (
        "ccg15v2_02_ret_precision_scan10",
        {"retrieval": {"precision_recovery": {"scan_candidates": 10}}},
        "Carry forward the strongest precision recovery scan winner from wave 1.",
    ),
    (
        "ccg15v2_03_ret_precision_conf085",
        {"retrieval": {"precision_recovery": {"min_confidence": 0.85}}},
        "Carry forward the tighter precision recovery confidence threshold.",
    ),
    (
        "ccg15v2_04_ret_coverage_add4",
        {"retrieval": {"coverage_recovery": {"max_additions": 4}}},
        "Carry forward the broader coverage recovery setting.",
    ),
    (
        "ccg15v2_05_ret_postmerge_60",
        {"retrieval": {"post_merge_candidates": 60}},
        "Carry forward the larger post-merge candidate surface.",
    ),
    (
        "ccg15v2_06_ctx_graph_025",
        {"context": {"submodular": {"w_rrf": 0.50, "w_graph": 0.25}}},
        "Carry forward the stronger graph-aware context packing balance.",
    ),
    (
        "ccg15v2_07_rank_bm25rescue_20",
        {"ranking": {"reranker": {"bm25_rescue_top_k": 20}}},
        "Carry forward the broader BM25 rescue set for reranking.",
    ),
    (
        "ccg15v2_08_ret_precision_scan12",
        {"retrieval": {"precision_recovery": {"scan_candidates": 12}}},
        "Local refinement above the scan10 winner to probe a slightly wider scan window.",
    ),
    (
        "ccg15v2_09_ret_precision_conf090",
        {"retrieval": {"precision_recovery": {"min_confidence": 0.90}}},
        "Local refinement above conf085 to test a stricter precision gate.",
    ),
    (
        "ccg15v2_10_ret_coverage_add5",
        {"retrieval": {"coverage_recovery": {"max_additions": 5}}},
        "Local refinement above coverage_add4 to test one more recovery insertion.",
    ),
    (
        "ccg15v2_11_ret_postmerge_70",
        {"retrieval": {"post_merge_candidates": 70}},
        "Local refinement above postmerge60 to probe a larger post-merge surface.",
    ),
    (
        "ccg15v2_12_combo_scan10_cov4",
        {
            "retrieval": {
                "precision_recovery": {"scan_candidates": 10},
                "coverage_recovery": {"max_additions": 4},
            }
        },
        "Interaction test combining the best scan expansion with stronger coverage recovery.",
    ),
    (
        "ccg15v2_13_combo_scan10_postmerge60",
        {
            "retrieval": {
                "precision_recovery": {"scan_candidates": 10},
                "post_merge_candidates": 60,
            }
        },
        "Interaction test combining the best scan expansion with a broader post-merge candidate set.",
    ),
    (
        "ccg15v2_14_combo_scan10_graph025",
        {
            "retrieval": {"precision_recovery": {"scan_candidates": 10}},
            "context": {"submodular": {"w_rrf": 0.50, "w_graph": 0.25}},
        },
        "Interaction test combining the best retrieval scan setting with stronger graph-aware context packing.",
    ),
    (
        "ccg15v2_15_combo_scan10_cov4_bm25rescue20",
        {
            "retrieval": {
                "precision_recovery": {"scan_candidates": 10},
                "coverage_recovery": {"max_additions": 4},
            },
            "ranking": {"reranker": {"bm25_rescue_top_k": 20}},
        },
        "Three-way interaction test combining the best scan, broader coverage recovery, and broader BM25 rescue.",
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
    "Base directory: `configs/tweaking/ccg_stage2_finetuning_v1`",
    "",
    "Each batch gets:",
    "- 1 experiment run",
    "- 1 Gemini judge run",
    "- 1 Cerebras SDK judge run",
    "",
    "Rules:",
    "- Do not chain batches together.",
    "- Run one config at a time.",
    "- If a judge fails, rerun only that judge command.",
    "- Do not rerun `run_experiment.py` unless the responses file is missing or corrupted.",
    "",
]

for item in index:
    name = item["name"]
    cfg_rel = f"configs/tweaking/ccg_stage2_finetuning_v1/{item['file']}"
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
