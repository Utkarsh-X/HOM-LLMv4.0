# BASELINE FREEZE METADATA (2026-02-14)

- Commit: 8dc1f46ad791c80c34fe3710ccefbb01a1a83e4b
- Canonical runtime config: `configs/default.yaml`
- Canonical judge config: `eval/judge_config.json`

## Canonical Diagnostics-Only Gate Command

`python eval/run_experiment.py --select 1,3,5,8,16,18 --telemetry-print --intelligence-levels l1,l2,l3 --reasoning-contracts --assertion-readability --diagnostic-layers --context-diagnostics --reuse-process --diagnostics-only --run-name <gate_name>`

## Canonical Judge Command

`python eval/run_judge.py --responses <run_dir>/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --output <run_dir>/judge_results.jsonl`

## Determinism Evidence Runs

- `eval/runs/eval_integrity_gate_a`
- `eval/runs/eval_integrity_gate_b`
- `eval/runs/config_cleanup_gate_a`
- `eval/runs/config_cleanup_gate_b`
- `eval/runs/tests_cleanup_gate_a`
- `eval/runs/tests_cleanup_gate_b`
- `eval/runs/unused_py_cleanup_gate_seq_a`
- `eval/runs/unused_py_cleanup_gate_seq_b`
