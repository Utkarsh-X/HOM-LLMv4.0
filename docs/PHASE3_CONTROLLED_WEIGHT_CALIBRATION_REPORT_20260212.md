# Phase 3 Controlled Weight Calibration Report

Date: 2026-02-12  
Workspace: `d:\HOM-LLM(v2.0)`

## Scope and Constraints Followed

This phase was executed under strict stabilization constraints:

- No new features added
- No dynamic modulation introduced
- No architecture changes
- No retrieval/context logic changes for calibration
- Set optimizer kept as simplified static objective surface

Objective used during these runs:

`objective = relevance + structural_coherence + coverage - redundancy - dispersion`

## Baseline Reference for Stability Checks

- Stability reference run for diversity and collapse: `run_20260212_phase1_simplified`
- Collapse criterion: any query with `blocks_selected <= 1`
- Diversity stability criterion: per-query `final_distinct_file_count` is not lower than Phase 1 simplified

## Config Variants Created (Ranking Weights Only)

1. `configs/phase3_covp10.yaml`
   - `w_coverage: 0.88` (+10%)
2. `configs/phase3_dispp10.yaml`
   - `w_dispersion: 0.44` (+10%)
3. `configs/phase3_redm10.yaml`
   - `w_redundancy: 0.45` (-10%)
4. `configs/phase3_covp8_dispp8.yaml`
   - `w_coverage: 0.864` (+8%)
   - `w_dispersion: 0.432` (+8%)
5. `configs/phase3_covp8_structp8.yaml`
   - `w_coverage: 0.864` (+8%)
   - `w_structural: 0.648` (+8%)

No other ranking weights were changed for these variants.

## Run IDs and Execution Notes

### Final runs used for evaluation

- +10% coverage: `run_20260212_phase3_covp10`
- +10% dispersion: `run_20260212_phase3_dispp10`
- -10% redundancy: `run_20260212_phase3_redm10_rerun`
- +8% coverage +8% dispersion: `run_20260212_phase3_covp8_dispp8_rerun`
- +8% coverage +8% structural: `run_20260212_phase3_covp8_structp8_rerun`

### Failure/retry history (important)

- Original `run_20260212_phase3_redm10` had generation failures (0/6 OK). It was rerun as `run_20260212_phase3_redm10_rerun` with 6/6 OK.
- Original `run_20260212_phase3_covp8_dispp8` had generation failures (0/6 OK). It was rerun as `run_20260212_phase3_covp8_dispp8_rerun`, partially recovered to 4/6 OK (Q16/Q18 still `status=ERROR`).
- Judge calls repeatedly hit Gemini free-tier quota ceilings (minute/day); missing judgments were backfilled where possible using `eval/judge_config.json` and `eval/judge_config_alt.json`.

## Results Summary

| Variant | Run | Generation OK/Total | Win Rate | Q3 Completeness | Q16 Completeness | Q18 Completeness | Collapse | Diversity Stable |
|---|---|---:|---:|---:|---:|---:|---|---|
| +10% coverage | `run_20260212_phase3_covp10` | 6/6 | 66.7% | 1 | 5 | 4 | No | Yes |
| +10% dispersion | `run_20260212_phase3_dispp10` | 6/6 | 50.0% | 1 | 5 | 4 | No | No |
| -10% redundancy | `run_20260212_phase3_redm10_rerun` | 6/6 | 66.7% | 1 | 5 | 4 | No | Yes |
| +8% coverage +8% dispersion | `run_20260212_phase3_covp8_dispp8_rerun` | 4/6 | 33.3% | 1 | 1 | 1 | No | No |
| +8% coverage +8% structural | `run_20260212_phase3_covp8_structp8_rerun` | 6/6 | 20.0% | 1 | 4 | 4 | No | Yes |

## Interpretation

1. Best observed win rate is tied:
   - `+10% coverage` and `-10% redundancy` both achieved **66.7%**.

2. Stability filters separate them from weaker variants:
   - Both best variants: no collapse, diversity stable.
   - `+10% dispersion` lost diversity stability.
   - `+8% coverage +8% dispersion` had both diversity instability and unresolved generation reliability.

3. Persistent weakness across all variants:
   - Q3 completeness remained low (`1`) in every tested setting.

4. Reliability note:
   - Variants with generation `ERROR` responses are structurally less reliable even if judged later.

## Recommended Selection

Primary recommendation for adoption:

- **`+10% coverage`** (`configs/phase3_covp10.yaml`)

Reason:

- Matches top win rate (66.7%)
- No collapse
- Diversity stable
- Fully successful generation run (6/6 OK)

Secondary viable option:

- `-10% redundancy` (`configs/phase3_redm10.yaml`) after rerun also reached 66.7% and remained stable.

## Artifacts Produced

- Configs:
  - `configs/phase3_covp10.yaml`
  - `configs/phase3_dispp10.yaml`
  - `configs/phase3_redm10.yaml`
  - `configs/phase3_covp8_dispp8.yaml`
  - `configs/phase3_covp8_structp8.yaml`

- Run folders:
  - `eval/runs/run_20260212_phase3_covp10`
  - `eval/runs/run_20260212_phase3_dispp10`
  - `eval/runs/run_20260212_phase3_redm10`
  - `eval/runs/run_20260212_phase3_redm10_rerun`
  - `eval/runs/run_20260212_phase3_covp8_dispp8`
  - `eval/runs/run_20260212_phase3_covp8_dispp8_rerun`
  - `eval/runs/run_20260212_phase3_covp8_structp8`
  - `eval/runs/run_20260212_phase3_covp8_structp8_rerun`

- Judge outputs (`judge_results_phase3.jsonl`) within each run folder where executed.

## Operational Notes

- Gemini quota ceilings were the primary external source of instability in this cycle.
- Retries and backfills were performed to maximize completeness of results.
- No optimizer architecture changes were introduced during Phase 3 calibration.

## Latest Direct Command Rerun (User-Requested)

Executed command:

`python eval/run_judge.py --responses eval/runs/run_20260212_phase3_redm10_rerun/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --output eval/runs/run_20260212_phase3_redm10_rerun/judge_results_phase3.jsonl`

Observed output for this rerun:

- Improved: 3
- Regressed: 2
- Equal: 1
- Candidate win rate: 60.0%

Notes:

- This direct rerun uses `eval/judge_config.json` and overwrites `eval/runs/run_20260212_phase3_redm10_rerun/judge_results_phase3.jsonl`.
- Earlier aggregation included mixed backfills across `eval/judge_config.json` and `eval/judge_config_alt.json` during quota-recovery; this can cause small run-to-run score variation.
