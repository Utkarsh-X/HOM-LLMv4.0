# Selection Drift Forensic Report (Addendum)

Date: 2026-02-13
Scope: Re-analysis of latest stable run `geneOK_run_w_dispersion0.4to0.2`

## 1. What I verified

- Latest run exists at `eval/runs/geneOK_run_w_dispersion0.4to0.2`.
- Judge file exists and has 6 parsed entries (`judge_results.jsonl`).
- Telemetry confirms this run executed with set-optimizer dispersion weight `0.2`.

Important clarification:
- Current `configs/default.yaml` now shows `w_dispersion: 0.1`.
- The analyzed run itself used `w_dispersion: 0.2` (from telemetry `weight_vector_used`).

## 2. Effect of lowering dispersion (0.4 -> 0.2)

Compared against `run_20260213_static_budget_baseline3200`.

### Aggregate (Q1,3,5,8,16,18)

- Avg context tokens: `1255.5 -> 1423.2`
- Avg blocks selected: `9.5 -> 10.5`
- Avg budget usage: `39.2% -> 44.5%`
- Avg distinct files: unchanged (`7.83`)

### Critical query change: Q3

- Context tokens: `130 -> 776`
- Blocks: `2 -> 6`
- Set coverage: `0.6 -> 0.7`
- Set relevance: `0.322 -> 0.465`

Selected blocks now include additional `optimization/query_optimizer.py` spans:
- `66-115`
- `117-125`
- `232-234`
- `261-266`

Interpretation:
- Lower dispersion pressure allowed same-file continuation chunks to remain gain-positive.
- This directly validates the previous frontier-suppression hypothesis.

## 3. Current quality status (raw judge scores, no reliance on improved/regressed labels)

From `eval/runs/geneOK_run_w_dispersion0.4to0.2/judge_results.jsonl`:

- Semantic correctness avg: candidate `5.000` vs baseline `4.833`
- Factual consistency avg: candidate `4.833` vs baseline `4.833`
- Completeness avg: candidate `4.333` vs baseline `4.500`
- Clarity avg: candidate `4.667` vs baseline `4.500`
- Relevance avg: candidate `5.000` vs baseline `5.000`
- Hallucination safety avg: candidate `4.667` vs baseline `4.500`
- Verbosity avg (lower better): candidate `3.000` vs baseline `3.000`
- Overall quality avg: candidate `4.500` vs baseline `4.333`

Reading:
- Overall is now slightly better on average.
- Main remaining gap is completeness consistency (especially Q16/Q18 style synthesis answers).

## 4. Updated root-cause confidence

- Dispersion overweight as early-stop contributor: **confirmed high confidence**.
- Context cap as root cause: **rejected**.
- Remaining issue after dispersion fix: **coverage/explanation sufficiency**, not token capacity.

## 5. Next minimal recommendation (no architecture changes)

1. Keep dispersion low (do not revert to 0.4).
2. Next single-parameter sweep: increase `w_coverage` by `+5%` to `+10%` with all else frozen.
3. Evaluate only raw metrics focus:
   - Completeness
   - Factual consistency
   - Hallucination safety
   - Overall quality
4. Track Q16/Q18 specifically; they are now the limiting cases.

## 6. Practical note

Your statement "w_dispersion = 2" likely meant `0.2`.
- Telemetry of latest stable run proves it used `0.2`.
- If dispersion were truly `2.0`, objective behavior would usually over-penalize concentration and likely destabilize selection.

