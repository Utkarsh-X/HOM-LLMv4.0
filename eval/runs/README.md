# Eval Runs Policy

## Active vs Archive

- Keep only current active and gate-validation runs in `eval/runs/`.
- Move superseded runs to `archive/eval_runs_YYYYMMDD/` with a manifest.

## Naming

- Standard run: `run_YYYYMMDD_HHMMSS`
- Stability gates: `<phase>_gate_run_a`, `<phase>_gate_run_b`
- Explicit experiment: `<short_label>` (must include date in run_info)

## Determinism Gate (Required)

- For each cleanup phase, run two consecutive diagnostics-only runs on queries `1,3,5,8,16,18`.
- Verification rule: selected block IDs per query must be identical between run A and run B.

## Judge Output Integrity

- Use `eval/judge_config.json` as canonical config.
- Do not append judge outputs by default.
- Keep one judge output file per run directory unless intentionally versioned.
