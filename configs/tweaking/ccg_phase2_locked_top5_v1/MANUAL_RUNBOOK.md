# Locked Top 5 Runbook

Base directory: `configs/tweaking/ccg_phase2_locked_top5_v1`

Rules:
- Run one config at a time.
- If a judge fails, rerun only that judge command.
- Do not rerun `run_experiment.py` unless `responses.jsonl` is missing or corrupted.

## ccglock5_01_baseline
Rationale: Locked stable baseline and new default config.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_phase2_locked_top5_v1/ccglock5_01_baseline.yaml --run-name ccglock5_01_baseline --telemetry-print
py eval/run_judge.py --responses eval/runs/ccglock5_01_baseline/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccglock5_01_baseline/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccglock5_01_baseline/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccglock5_01_baseline/judge_results__cerebras_manual.jsonl
```

## ccglock5_02_rank_bm25rescue_20
Rationale: Best cross-judge consensus winner from phase 2.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_phase2_locked_top5_v1/ccglock5_02_rank_bm25rescue_20.yaml --run-name ccglock5_02_rank_bm25rescue_20 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccglock5_02_rank_bm25rescue_20/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccglock5_02_rank_bm25rescue_20/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccglock5_02_rank_bm25rescue_20/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccglock5_02_rank_bm25rescue_20/judge_results__cerebras_manual.jsonl
```

## ccglock5_03_ret_precision_scan10
Rationale: Best retrieval scan-direction winner carried into lock set.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_phase2_locked_top5_v1/ccglock5_03_ret_precision_scan10.yaml --run-name ccglock5_03_ret_precision_scan10 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccglock5_03_ret_precision_scan10/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccglock5_03_ret_precision_scan10/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccglock5_03_ret_precision_scan10/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccglock5_03_ret_precision_scan10/judge_results__cerebras_manual.jsonl
```

## ccglock5_04_ret_precision_conf085
Rationale: Most stable precision-confidence winner from phase 2.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_phase2_locked_top5_v1/ccglock5_04_ret_precision_conf085.yaml --run-name ccglock5_04_ret_precision_conf085 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccglock5_04_ret_precision_conf085/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccglock5_04_ret_precision_conf085/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccglock5_04_ret_precision_conf085/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccglock5_04_ret_precision_conf085/judge_results__cerebras_manual.jsonl
```

## ccglock5_05_ret_precision_scan12
Rationale: Highest-scoring scan refinement kept as the fifth locked candidate.

```powershell
py eval/run_experiment.py --select 1-20 --config configs/tweaking/ccg_phase2_locked_top5_v1/ccglock5_05_ret_precision_scan12.yaml --run-name ccglock5_05_ret_precision_scan12 --telemetry-print
py eval/run_judge.py --responses eval/runs/ccglock5_05_ret_precision_scan12/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --output eval/runs/ccglock5_05_ret_precision_scan12/judge_results__gemini_manual.jsonl
py eval/run_judge.py --responses eval/runs/ccglock5_05_ret_precision_scan12/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccglock5_05_ret_precision_scan12/judge_results__cerebras_manual.jsonl
```
