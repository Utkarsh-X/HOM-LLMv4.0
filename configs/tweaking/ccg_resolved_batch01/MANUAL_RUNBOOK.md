# Manual Runbook

Base directory: `configs/tweaking/ccg_resolved_batch01`

Each variant gets:
- 1 experiment run
- 1 Gemini judge run
- 1 Cerebras SDK judge run

## ccg_resolved_baseline
Rationale: Resolved winning CCG config with all fallback defaults materialized.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_resolved_baseline.yaml --run-name ccg_resolved_baseline --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_resolved_baseline/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_resolved_baseline/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_resolved_baseline/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_resolved_baseline/judge_results__cerebras_manual.jsonl
```

## ccg_ret_precision_add2
Rationale: Tighten precision recovery breadth by one step.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_ret_precision_add2.yaml --run-name ccg_ret_precision_add2 --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_ret_precision_add2/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_ret_precision_add2/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_ret_precision_add2/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_ret_precision_add2/judge_results__cerebras_manual.jsonl
```

## ccg_ret_precision_add4
Rationale: Loosen precision recovery breadth by one step.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_ret_precision_add4.yaml --run-name ccg_ret_precision_add4 --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_ret_precision_add4/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_ret_precision_add4/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_ret_precision_add4/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_ret_precision_add4/judge_results__cerebras_manual.jsonl
```

## ccg_ret_coverage_add2
Rationale: Reduce coverage recovery insertions.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_ret_coverage_add2.yaml --run-name ccg_ret_coverage_add2 --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_ret_coverage_add2/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_ret_coverage_add2/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_ret_coverage_add2/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_ret_coverage_add2/judge_results__cerebras_manual.jsonl
```

## ccg_ret_coverage_add4
Rationale: Increase coverage recovery insertions.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_ret_coverage_add4.yaml --run-name ccg_ret_coverage_add4 --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_ret_coverage_add4/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_ret_coverage_add4/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_ret_coverage_add4/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_ret_coverage_add4/judge_results__cerebras_manual.jsonl
```

## ccg_ret_postmerge_40
Rationale: Smaller post-merge candidate surface.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_ret_postmerge_40.yaml --run-name ccg_ret_postmerge_40 --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_ret_postmerge_40/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_ret_postmerge_40/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_ret_postmerge_40/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_ret_postmerge_40/judge_results__cerebras_manual.jsonl
```

## ccg_ret_postmerge_60
Rationale: Larger post-merge candidate surface.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_ret_postmerge_60.yaml --run-name ccg_ret_postmerge_60 --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_ret_postmerge_60/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_ret_postmerge_60/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_ret_postmerge_60/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_ret_postmerge_60/judge_results__cerebras_manual.jsonl
```

## ccg_ctx_dynstep_300
Rationale: Smaller dynamic budget expansion step.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_ctx_dynstep_300.yaml --run-name ccg_ctx_dynstep_300 --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_ctx_dynstep_300/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_ctx_dynstep_300/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_ctx_dynstep_300/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_ctx_dynstep_300/judge_results__cerebras_manual.jsonl
```

## ccg_ctx_dynstep_500
Rationale: Larger dynamic budget expansion step.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_ctx_dynstep_500.yaml --run-name ccg_ctx_dynstep_500 --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_ctx_dynstep_500/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_ctx_dynstep_500/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_ctx_dynstep_500/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_ctx_dynstep_500/judge_results__cerebras_manual.jsonl
```

## ccg_ctx_dynexp_1
Rationale: More conservative dynamic expansion count.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_ctx_dynexp_1.yaml --run-name ccg_ctx_dynexp_1 --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_ctx_dynexp_1/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_ctx_dynexp_1/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_ctx_dynexp_1/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_ctx_dynexp_1/judge_results__cerebras_manual.jsonl
```

## ccg_ctx_dynexp_3
Rationale: More aggressive dynamic expansion count.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_ctx_dynexp_3.yaml --run-name ccg_ctx_dynexp_3 --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_ctx_dynexp_3/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_ctx_dynexp_3/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_ctx_dynexp_3/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_ctx_dynexp_3/judge_results__cerebras_manual.jsonl
```

## ccg_ctx_relgate_020
Rationale: Loosen relevance gate to admit more blocks.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_ctx_relgate_020.yaml --run-name ccg_ctx_relgate_020 --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_ctx_relgate_020/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_ctx_relgate_020/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_ctx_relgate_020/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_ctx_relgate_020/judge_results__cerebras_manual.jsonl
```

## ccg_ctx_relgate_030
Rationale: Tighten relevance gate to reject weaker blocks.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_ctx_relgate_030.yaml --run-name ccg_ctx_relgate_030 --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_ctx_relgate_030/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_ctx_relgate_030/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_ctx_relgate_030/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_ctx_relgate_030/judge_results__cerebras_manual.jsonl
```

## ccg_ctx_graph_015
Rationale: Reduce graph bias, return weight to RRF.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_ctx_graph_015.yaml --run-name ccg_ctx_graph_015 --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_ctx_graph_015/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_ctx_graph_015/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_ctx_graph_015/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_ctx_graph_015/judge_results__cerebras_manual.jsonl
```

## ccg_ctx_graph_025
Rationale: Increase graph bias, reduce RRF slightly.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_ctx_graph_025.yaml --run-name ccg_ctx_graph_025 --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_ctx_graph_025/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_ctx_graph_025/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_ctx_graph_025/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_ctx_graph_025/judge_results__cerebras_manual.jsonl
```

## ccg_rank_bm25rescue_10
Rationale: Reduce BM25 rescue set for reranker.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_rank_bm25rescue_10.yaml --run-name ccg_rank_bm25rescue_10 --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_rank_bm25rescue_10/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_rank_bm25rescue_10/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_rank_bm25rescue_10/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_rank_bm25rescue_10/judge_results__cerebras_manual.jsonl
```

## ccg_rank_bm25rescue_20
Rationale: Increase BM25 rescue set for reranker.

```powershell
python eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_resolved_batch01/ccg_rank_bm25rescue_20.yaml --run-name ccg_rank_bm25rescue_20 --telemetry-print
python eval/run_judge.py --responses eval/runs/ccg_rank_bm25rescue_20/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccg_rank_bm25rescue_20/judge_results__gemini_manual.jsonl
python eval/run_judge.py --responses eval/runs/ccg_rank_bm25rescue_20/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_rank_bm25rescue_20/judge_results__cerebras_manual.jsonl
```

