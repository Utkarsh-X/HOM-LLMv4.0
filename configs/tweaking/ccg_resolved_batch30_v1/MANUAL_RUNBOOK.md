# Manual Runbook

Base directory: `configs/tweaking/ccg_resolved_batch30_v1`

Each batch gets:
- 1 experiment run
- 1 Gemini judge run
- 1 Cerebras SDK judge run

Rules:
- Do not chain batches together.
- Run one batch at a time.
- If Gemini judge fails, rerun only the Gemini judge command for that batch.
- If Cerebras judge fails, rerun only the Cerebras judge command for that batch.
- If a partial judge output file exists, delete it first and rerun the same command.
- Do not rerun `run_experiment.py` unless the responses file is missing or corrupted.

## ccg30_01_baseline
Rationale: Resolved winning CCG config with all fallback defaults materialized.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_01_baseline.yaml --run-name ccg30_01_baseline --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_01_baseline/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_01_baseline/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_01_baseline/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_01_baseline/judge_results__cerebras_manual.jsonl
```

## ccg30_02_ret_precision_add2
Rationale: Reduce precision recovery additions below the resolved baseline.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_02_ret_precision_add2.yaml --run-name ccg30_02_ret_precision_add2 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_02_ret_precision_add2/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_02_ret_precision_add2/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_02_ret_precision_add2/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_02_ret_precision_add2/judge_results__cerebras_manual.jsonl
```

## ccg30_03_ret_precision_add4
Rationale: Increase precision recovery additions above the resolved baseline.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_03_ret_precision_add4.yaml --run-name ccg30_03_ret_precision_add4 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_03_ret_precision_add4/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_03_ret_precision_add4/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_03_ret_precision_add4/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_03_ret_precision_add4/judge_results__cerebras_manual.jsonl
```

## ccg30_04_ret_precision_scan6
Rationale: Narrow the precision recovery scan window.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_04_ret_precision_scan6.yaml --run-name ccg30_04_ret_precision_scan6 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_04_ret_precision_scan6/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_04_ret_precision_scan6/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_04_ret_precision_scan6/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_04_ret_precision_scan6/judge_results__cerebras_manual.jsonl
```

## ccg30_05_ret_precision_scan10
Rationale: Widen the precision recovery scan window.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_05_ret_precision_scan10.yaml --run-name ccg30_05_ret_precision_scan10 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_05_ret_precision_scan10/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_05_ret_precision_scan10/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_05_ret_precision_scan10/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_05_ret_precision_scan10/judge_results__cerebras_manual.jsonl
```

## ccg30_06_ret_precision_conf075
Rationale: Loosen precision recovery confidence threshold.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_06_ret_precision_conf075.yaml --run-name ccg30_06_ret_precision_conf075 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_06_ret_precision_conf075/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_06_ret_precision_conf075/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_06_ret_precision_conf075/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_06_ret_precision_conf075/judge_results__cerebras_manual.jsonl
```

## ccg30_07_ret_precision_conf085
Rationale: Tighten precision recovery confidence threshold.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_07_ret_precision_conf085.yaml --run-name ccg30_07_ret_precision_conf085 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_07_ret_precision_conf085/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_07_ret_precision_conf085/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_07_ret_precision_conf085/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_07_ret_precision_conf085/judge_results__cerebras_manual.jsonl
```

## ccg30_08_ret_coverage_add2
Rationale: Reduce coverage recovery insertions.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_08_ret_coverage_add2.yaml --run-name ccg30_08_ret_coverage_add2 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_08_ret_coverage_add2/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_08_ret_coverage_add2/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_08_ret_coverage_add2/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_08_ret_coverage_add2/judge_results__cerebras_manual.jsonl
```

## ccg30_09_ret_coverage_add4
Rationale: Increase coverage recovery insertions.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_09_ret_coverage_add4.yaml --run-name ccg30_09_ret_coverage_add4 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_09_ret_coverage_add4/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_09_ret_coverage_add4/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_09_ret_coverage_add4/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_09_ret_coverage_add4/judge_results__cerebras_manual.jsonl
```

## ccg30_10_ret_postmerge_40
Rationale: Shrink the post-merge candidate surface.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_10_ret_postmerge_40.yaml --run-name ccg30_10_ret_postmerge_40 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_10_ret_postmerge_40/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_10_ret_postmerge_40/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_10_ret_postmerge_40/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_10_ret_postmerge_40/judge_results__cerebras_manual.jsonl
```

## ccg30_11_ret_postmerge_60
Rationale: Expand the post-merge candidate surface.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_11_ret_postmerge_60.yaml --run-name ccg30_11_ret_postmerge_60 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_11_ret_postmerge_60/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_11_ret_postmerge_60/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_11_ret_postmerge_60/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_11_ret_postmerge_60/judge_results__cerebras_manual.jsonl
```

## ccg30_12_ctx_dynstep_300
Rationale: Use a smaller dynamic budget expansion step.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_12_ctx_dynstep_300.yaml --run-name ccg30_12_ctx_dynstep_300 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_12_ctx_dynstep_300/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_12_ctx_dynstep_300/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_12_ctx_dynstep_300/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_12_ctx_dynstep_300/judge_results__cerebras_manual.jsonl
```

## ccg30_13_ctx_dynstep_500
Rationale: Use a larger dynamic budget expansion step.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_13_ctx_dynstep_500.yaml --run-name ccg30_13_ctx_dynstep_500 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_13_ctx_dynstep_500/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_13_ctx_dynstep_500/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_13_ctx_dynstep_500/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_13_ctx_dynstep_500/judge_results__cerebras_manual.jsonl
```

## ccg30_14_ctx_dynexp_1
Rationale: Limit dynamic budget to a single expansion.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_14_ctx_dynexp_1.yaml --run-name ccg30_14_ctx_dynexp_1 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_14_ctx_dynexp_1/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_14_ctx_dynexp_1/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_14_ctx_dynexp_1/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_14_ctx_dynexp_1/judge_results__cerebras_manual.jsonl
```

## ccg30_15_ctx_dynexp_3
Rationale: Allow one more dynamic budget expansion than the resolved baseline.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_15_ctx_dynexp_3.yaml --run-name ccg30_15_ctx_dynexp_3 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_15_ctx_dynexp_3/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_15_ctx_dynexp_3/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_15_ctx_dynexp_3/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_15_ctx_dynexp_3/judge_results__cerebras_manual.jsonl
```

## ccg30_16_ctx_relgate_020
Rationale: Loosen the relevance gate to admit weaker blocks.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_16_ctx_relgate_020.yaml --run-name ccg30_16_ctx_relgate_020 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_16_ctx_relgate_020/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_16_ctx_relgate_020/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_16_ctx_relgate_020/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_16_ctx_relgate_020/judge_results__cerebras_manual.jsonl
```

## ccg30_17_ctx_relgate_030
Rationale: Tighten the relevance gate to reject weaker blocks.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_17_ctx_relgate_030.yaml --run-name ccg30_17_ctx_relgate_030 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_17_ctx_relgate_030/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_17_ctx_relgate_030/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_17_ctx_relgate_030/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_17_ctx_relgate_030/judge_results__cerebras_manual.jsonl
```

## ccg30_18_ctx_graph_015
Rationale: Reduce graph weight and return that mass to RRF.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_18_ctx_graph_015.yaml --run-name ccg30_18_ctx_graph_015 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_18_ctx_graph_015/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_18_ctx_graph_015/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_18_ctx_graph_015/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_18_ctx_graph_015/judge_results__cerebras_manual.jsonl
```

## ccg30_19_ctx_graph_025
Rationale: Increase graph weight and reduce RRF slightly.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_19_ctx_graph_025.yaml --run-name ccg30_19_ctx_graph_025 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_19_ctx_graph_025/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_19_ctx_graph_025/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_19_ctx_graph_025/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_19_ctx_graph_025/judge_results__cerebras_manual.jsonl
```

## ccg30_20_ctx_unresblocks_1
Rationale: Make unresolved evidence injection more conservative.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_20_ctx_unresblocks_1.yaml --run-name ccg30_20_ctx_unresblocks_1 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_20_ctx_unresblocks_1/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_20_ctx_unresblocks_1/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_20_ctx_unresblocks_1/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_20_ctx_unresblocks_1/judge_results__cerebras_manual.jsonl
```

## ccg30_21_ctx_unresblocks_3
Rationale: Make unresolved evidence injection more aggressive.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_21_ctx_unresblocks_3.yaml --run-name ccg30_21_ctx_unresblocks_3 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_21_ctx_unresblocks_3/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_21_ctx_unresblocks_3/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_21_ctx_unresblocks_3/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_21_ctx_unresblocks_3/judge_results__cerebras_manual.jsonl
```

## ccg30_22_rank_bm25rescue_10
Rationale: Reduce the BM25 rescue set passed into reranking.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_22_rank_bm25rescue_10.yaml --run-name ccg30_22_rank_bm25rescue_10 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_22_rank_bm25rescue_10/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_22_rank_bm25rescue_10/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_22_rank_bm25rescue_10/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_22_rank_bm25rescue_10/judge_results__cerebras_manual.jsonl
```

## ccg30_23_rank_bm25rescue_20
Rationale: Increase the BM25 rescue set passed into reranking.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_23_rank_bm25rescue_20.yaml --run-name ccg30_23_rank_bm25rescue_20 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_23_rank_bm25rescue_20/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_23_rank_bm25rescue_20/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_23_rank_bm25rescue_20/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_23_rank_bm25rescue_20/judge_results__cerebras_manual.jsonl
```

## ccg30_24_rank_topm_25
Rationale: Rerank a smaller candidate set.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_24_rank_topm_25.yaml --run-name ccg30_24_rank_topm_25 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_24_rank_topm_25/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_24_rank_topm_25/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_24_rank_topm_25/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_24_rank_topm_25/judge_results__cerebras_manual.jsonl
```

## ccg30_25_rank_topm_45
Rationale: Rerank a larger candidate set.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_25_rank_topm_45.yaml --run-name ccg30_25_rank_topm_45 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_25_rank_topm_45/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_25_rank_topm_45/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_25_rank_topm_45/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_25_rank_topm_45/judge_results__cerebras_manual.jsonl
```

## ccg30_26_rank_gate_margin_015
Rationale: Loosen reranker gating margin.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_26_rank_gate_margin_015.yaml --run-name ccg30_26_rank_gate_margin_015 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_26_rank_gate_margin_015/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_26_rank_gate_margin_015/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_26_rank_gate_margin_015/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_26_rank_gate_margin_015/judge_results__cerebras_manual.jsonl
```

## ccg30_27_rank_gate_margin_025
Rationale: Tighten reranker gating margin.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_27_rank_gate_margin_025.yaml --run-name ccg30_27_rank_gate_margin_025 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_27_rank_gate_margin_025/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_27_rank_gate_margin_025/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_27_rank_gate_margin_025/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_27_rank_gate_margin_025/judge_results__cerebras_manual.jsonl
```

## ccg30_28_combo_retrieval_breadth_high
Rationale: Expand retrieval breadth across precision recovery, coverage recovery, and post-merge candidates together.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_28_combo_retrieval_breadth_high.yaml --run-name ccg30_28_combo_retrieval_breadth_high --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_28_combo_retrieval_breadth_high/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_28_combo_retrieval_breadth_high/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_28_combo_retrieval_breadth_high/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_28_combo_retrieval_breadth_high/judge_results__cerebras_manual.jsonl
```

## ccg30_29_combo_context_conservative
Rationale: Conservative context regime with tighter gates and lower rescue allowance.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_29_combo_context_conservative.yaml --run-name ccg30_29_combo_context_conservative --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_29_combo_context_conservative/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_29_combo_context_conservative/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_29_combo_context_conservative/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_29_combo_context_conservative/judge_results__cerebras_manual.jsonl
```

## ccg30_30_combo_context_aggressive
Rationale: Aggressive context regime with broader expansion and stronger rescue allowance.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch30_v1/ccg30_30_combo_context_aggressive.yaml --run-name ccg30_30_combo_context_aggressive --telemetry-print
py eval/run_judge.py --responses eval/runs/ccg30_30_combo_context_aggressive/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg30_30_combo_context_aggressive/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccg30_30_combo_context_aggressive/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg30_30_combo_context_aggressive/judge_results__cerebras_manual.jsonl
```
