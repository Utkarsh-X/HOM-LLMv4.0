# Manual Runbook

Base directory: `configs/tweaking/ccg_stage2_finetuning_v1`

Each batch gets:
- 1 experiment run
- 1 Gemini judge run
- 1 Cerebras SDK judge run

Rules:
- Do not chain batches together.
- Run one config at a time.
- If a judge fails, rerun only that judge command.
- Do not rerun `run_experiment.py` unless the responses file is missing or corrupted.

## ccg15v2_01_baseline
Rationale: Resolved winning CCG config with all fallback defaults materialized.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_stage2_finetuning_v1/ccg15v2_01_baseline.yaml --run-name ccg15v2_01_baseline --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg15v2_01_baseline/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg15v2_01_baseline/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg15v2_01_baseline/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg15v2_01_baseline/judge_results__cerebras_manual.jsonl
```

## ccg15v2_02_ret_precision_scan10
Rationale: Carry forward the strongest precision recovery scan winner from wave 1.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_stage2_finetuning_v1/ccg15v2_02_ret_precision_scan10.yaml --run-name ccg15v2_02_ret_precision_scan10 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg15v2_02_ret_precision_scan10/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg15v2_02_ret_precision_scan10/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg15v2_02_ret_precision_scan10/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg15v2_02_ret_precision_scan10/judge_results__cerebras_manual.jsonl
```

## ccg15v2_03_ret_precision_conf085
Rationale: Carry forward the tighter precision recovery confidence threshold.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_stage2_finetuning_v1/ccg15v2_03_ret_precision_conf085.yaml --run-name ccg15v2_03_ret_precision_conf085 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg15v2_03_ret_precision_conf085/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg15v2_03_ret_precision_conf085/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg15v2_03_ret_precision_conf085/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg15v2_03_ret_precision_conf085/judge_results__cerebras_manual.jsonl
```

## ccg15v2_04_ret_coverage_add4
Rationale: Carry forward the broader coverage recovery setting.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_stage2_finetuning_v1/ccg15v2_04_ret_coverage_add4.yaml --run-name ccg15v2_04_ret_coverage_add4 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg15v2_04_ret_coverage_add4/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg15v2_04_ret_coverage_add4/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg15v2_04_ret_coverage_add4/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg15v2_04_ret_coverage_add4/judge_results__cerebras_manual.jsonl
```

## ccg15v2_05_ret_postmerge_60
Rationale: Carry forward the larger post-merge candidate surface.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_stage2_finetuning_v1/ccg15v2_05_ret_postmerge_60.yaml --run-name ccg15v2_05_ret_postmerge_60 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg15v2_05_ret_postmerge_60/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg15v2_05_ret_postmerge_60/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg15v2_05_ret_postmerge_60/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg15v2_05_ret_postmerge_60/judge_results__cerebras_manual.jsonl
```

## ccg15v2_06_ctx_graph_025
Rationale: Carry forward the stronger graph-aware context packing balance.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_stage2_finetuning_v1/ccg15v2_06_ctx_graph_025.yaml --run-name ccg15v2_06_ctx_graph_025 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg15v2_06_ctx_graph_025/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg15v2_06_ctx_graph_025/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg15v2_06_ctx_graph_025/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg15v2_06_ctx_graph_025/judge_results__cerebras_manual.jsonl
```

## ccg15v2_07_rank_bm25rescue_20
Rationale: Carry forward the broader BM25 rescue set for reranking.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_stage2_finetuning_v1/ccg15v2_07_rank_bm25rescue_20.yaml --run-name ccg15v2_07_rank_bm25rescue_20 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg15v2_07_rank_bm25rescue_20/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg15v2_07_rank_bm25rescue_20/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg15v2_07_rank_bm25rescue_20/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg15v2_07_rank_bm25rescue_20/judge_results__cerebras_manual.jsonl
```

## ccg15v2_08_ret_precision_scan12
Rationale: Local refinement above the scan10 winner to probe a slightly wider scan window.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_stage2_finetuning_v1/ccg15v2_08_ret_precision_scan12.yaml --run-name ccg15v2_08_ret_precision_scan12 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg15v2_08_ret_precision_scan12/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg15v2_08_ret_precision_scan12/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg15v2_08_ret_precision_scan12/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg15v2_08_ret_precision_scan12/judge_results__cerebras_manual.jsonl
```

## ccg15v2_09_ret_precision_conf090
Rationale: Local refinement above conf085 to test a stricter precision gate.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_stage2_finetuning_v1/ccg15v2_09_ret_precision_conf090.yaml --run-name ccg15v2_09_ret_precision_conf090 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg15v2_09_ret_precision_conf090/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg15v2_09_ret_precision_conf090/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg15v2_09_ret_precision_conf090/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg15v2_09_ret_precision_conf090/judge_results__cerebras_manual.jsonl
```

## ccg15v2_10_ret_coverage_add5
Rationale: Local refinement above coverage_add4 to test one more recovery insertion.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_stage2_finetuning_v1/ccg15v2_10_ret_coverage_add5.yaml --run-name ccg15v2_10_ret_coverage_add5 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg15v2_10_ret_coverage_add5/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg15v2_10_ret_coverage_add5/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg15v2_10_ret_coverage_add5/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg15v2_10_ret_coverage_add5/judge_results__cerebras_manual.jsonl
```

## ccg15v2_11_ret_postmerge_70
Rationale: Local refinement above postmerge60 to probe a larger post-merge surface.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_stage2_finetuning_v1/ccg15v2_11_ret_postmerge_70.yaml --run-name ccg15v2_11_ret_postmerge_70 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg15v2_11_ret_postmerge_70/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg15v2_11_ret_postmerge_70/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg15v2_11_ret_postmerge_70/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg15v2_11_ret_postmerge_70/judge_results__cerebras_manual.jsonl
```

## ccg15v2_12_combo_scan10_cov4
Rationale: Interaction test combining the best scan expansion with stronger coverage recovery.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_stage2_finetuning_v1/ccg15v2_12_combo_scan10_cov4.yaml --run-name ccg15v2_12_combo_scan10_cov4 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg15v2_12_combo_scan10_cov4/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg15v2_12_combo_scan10_cov4/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg15v2_12_combo_scan10_cov4/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg15v2_12_combo_scan10_cov4/judge_results__cerebras_manual.jsonl
```

## ccg15v2_13_combo_scan10_postmerge60
Rationale: Interaction test combining the best scan expansion with a broader post-merge candidate set.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_stage2_finetuning_v1/ccg15v2_13_combo_scan10_postmerge60.yaml --run-name ccg15v2_13_combo_scan10_postmerge60 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg15v2_13_combo_scan10_postmerge60/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg15v2_13_combo_scan10_postmerge60/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg15v2_13_combo_scan10_postmerge60/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg15v2_13_combo_scan10_postmerge60/judge_results__cerebras_manual.jsonl
```

## ccg15v2_14_combo_scan10_graph025
Rationale: Interaction test combining the best retrieval scan setting with stronger graph-aware context packing.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_stage2_finetuning_v1/ccg15v2_14_combo_scan10_graph025.yaml --run-name ccg15v2_14_combo_scan10_graph025 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg15v2_14_combo_scan10_graph025/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg15v2_14_combo_scan10_graph025/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg15v2_14_combo_scan10_graph025/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg15v2_14_combo_scan10_graph025/judge_results__cerebras_manual.jsonl
```

## ccg15v2_15_combo_scan10_cov4_bm25rescue20
Rationale: Three-way interaction test combining the best scan, broader coverage recovery, and broader BM25 rescue.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_stage2_finetuning_v1/ccg15v2_15_combo_scan10_cov4_bm25rescue20.yaml --run-name ccg15v2_15_combo_scan10_cov4_bm25rescue20 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg15v2_15_combo_scan10_cov4_bm25rescue20/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg15v2_15_combo_scan10_cov4_bm25rescue20/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg15v2_15_combo_scan10_cov4_bm25rescue20/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg15v2_15_combo_scan10_cov4_bm25rescue20/judge_results__cerebras_manual.jsonl
```
