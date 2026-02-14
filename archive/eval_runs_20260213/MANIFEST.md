# Eval Runs Archive Manifest (2026-02-13)

Purpose: archive superseded evaluation run folders while keeping current stability-gate and latest active runs in `eval/runs/`.

## Moved Folders

- `eval/runs/run_20260210_125413` -> `archive/eval_runs_20260213/run_20260210_125413`
- `eval/runs/run_repro_phase3_covp10` -> `archive/eval_runs_20260213/run_repro_phase3_covp10`
- `eval/runs/run_repro_phase3_covp110` -> `archive/eval_runs_20260213/run_repro_phase3_covp110`
- `eval/runs/run_w_dispersion0.4to0.2` -> `archive/eval_runs_20260213/run_w_dispersion0.4to0.2`

## Kept Active In `eval/runs/`

- `geneOK_run_w_dispersion0.4to0.2`
- `stability_gate_run_a`, `stability_gate_run_b`
- `ranking_cleanup_gate_a`, `ranking_cleanup_gate_b`
- `context_cleanup_gate_a`, `context_cleanup_gate_b`
- `budget_cleanup_gate_a`, `budget_cleanup_gate_b`
- `retrieval_cleanup_gate_a`, `retrieval_cleanup_gate_b`
- `run_20260213_172422`, `run_20260213_185914`, `run_20260213_185944`, `run_20260213_190211`

## Reversal Procedure

1. Move any folder from `archive/eval_runs_20260213/` back into `eval/runs/`.
2. Keep this manifest alongside archived folders.
3. Do not merge archived and active runs into the same output targets.
