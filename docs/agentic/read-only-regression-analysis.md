# Read-Only Agentic Regression Analysis

## Scope

This note analyzes the three known regressions from `ccg_stage2_agentic_ro3_full20_probe_v2` before any execution or patch-capable mode work.

Regressed queries:

- Query 16: `How does BatchProcessor handle partial failures and implement at-least-once semantics?`
- Query 18: `How do all 5 optimizer rules combine with execution timing and plan caching in complex queries?`
- Query 20: `Summarize expected outcomes of a stress test with 100 concurrent requests (errors, pool saturation, cache distribution, fallbacks, latency percentiles).`

## Evidence Reviewed

Artifacts inspected:

- `eval/runs/ccg_stage2_agentic_ro3_full20_probe_v2/judge_results__cerebras_manual.jsonl`
- `eval/runs/ccg_stage2_agentic_ro3_full20_probe_v2/responses.jsonl`
- `eval/runs/ccg_stage2_agentic_ro3_full20_probe_v2/generated_answers/query_16.txt`
- `eval/runs/ccg_stage2_agentic_ro3_full20_probe_v2/generated_answers/query_18.txt`
- `eval/runs/ccg_stage2_agentic_ro3_full20_probe_v2/generated_answers/query_20.txt`
- `artifacts/runs/c4ae05e8-fcea-4268-bb29-f6b9cec6cc2a/*`
- `artifacts/runs/bdc91adc-e49b-4a61-9484-e404dbbe99e1/*`
- `artifacts/runs/4bb44a25-0f92-4111-a6a3-d816de3db89b/*`

## Observed Failure Pattern

The regressions were not simple retrieval misses. Relevant evidence was present, at least partially:

- Query 16 retrieved `async_jobs/batch_processor.py` and had `BatchProcessor_process` in the top 10 retrieval candidates.
- Query 18 retrieved `optimization/query_planner.py`, `optimization/query_optimizer.py`, and `optimization/execution_engine.py`.
- Query 20 retrieved pool, cache, metrics, config, and API evidence across the relevant subsystems.

The primary failure was answer synthesis:

- Query 16 answered with generic batch-processing best practices instead of directly explaining the observed `BatchProcessor.process` failure behavior.
- Query 18 over-emphasized integration uncertainty and became verbose, reducing the quality of the requested interaction summary.
- Query 20 listed components and possible errors instead of producing a cause-effect stress-test outcome forecast.

## Planner Loop Findings

The read-only agentic planner did not reliably produce parseable decisions in the inspected run:

- Query 16: 3 iterations; planner parse failures caused fallback retrieval broadening until max iterations.
- Query 18: 2 iterations; planner decisions were partial parses.
- Query 20: 2 iterations; planner decisions were partial parses.

This means the inspected canary was not exercising a strong planner. It was mostly exercising fallback broadening plus the final generator.

The current branch now has tested parser fallback behavior in `src/homllm/agent/orchestrator.py`, including:

- partial action extraction from malformed planner output
- fallback to `retrieve_context` before max iterations
- forced `answer` at max iterations
- provider-error fallback to `answer`
- tests for valid parsed planner decisions

## Answer-Shape Findings

The regressed outputs use sections such as:

- `Repo Finding`
- `General Guidance`
- `Design Note`

Those sections come from absent-code answer-shape behavior in `src/homllm/intelligence/answer_contracts.py`.

For these three queries, that answer shape was harmful when direct evidence existed but claim coverage remained low. It encouraged the model to separate repo findings from generic guidance instead of synthesizing the actual mechanism.

Current `runtime/run_query.py` already includes stronger evidence-first guardrails than the inspected April outputs followed, including:

- answer asked scope first
- avoid unrelated components or methods
- include concrete in-code effects when present
- include operational details when present
- avoid dedicated unresolved/gap sections unless explicitly requested
- do not speculate about missing integration gaps unless directly evidenced and necessary

Because of that, the next step should be a focused rerun before making another code change.

## Working Root Cause Hypothesis

The regressions likely came from a combination of:

1. Unreliable planner JSON causing fallback-only read-only iterations.
2. Low claim coverage triggering absent-code-style answer shaping.
3. The generator following generic guidance sections too strongly when the user asked for concrete synthesis.
4. No final synthesis gate that checks whether the answer is a catalog/guidance dump versus an outcome/mechanism answer.

## What Not To Do

Do not add execution or patch mode to fix these regressions.

Do not broaden retrieval again by default. The evidence was often already present.

Do not remove safety grounding rules. The problem is not that the system was too grounded; the problem is that it failed to synthesize grounded evidence into the requested answer shape.

## Next Validation Step

Run a focused canary for queries 16, 18, and 20 against the current branch and current prompt/runtime behavior.

Recommended command when the full environment is available:

```powershell
python eval/run_experiment.py --select 16,18,20 --config configs/agentic/ccg_stage2_canary_v1/ccg_stage2_agentic_ro3.yaml --run-name ccg_stage2_agentic_ro3_regression_probe_current --telemetry-print
```

Then judge only that run:

```powershell
python eval/run_judge.py --responses eval/runs/ccg_stage2_agentic_ro3_regression_probe_current/responses.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider cerebras_sdk --output eval/runs/ccg_stage2_agentic_ro3_regression_probe_current/judge_results__cerebras_manual.jsonl
```

If the rerun still regresses, the first code fix should target answer-shape contracts, not retrieval breadth.

## Candidate Fix If Rerun Still Regresses

Add a synthesis-first answer contract for low-coverage-but-evidence-present queries:

- If direct evidence exists for named symbols or core query terms, do not enter `Repo Finding` / `General Guidance` absent-code structure.
- For mechanism queries, require `Observed Behavior`, `Failure / Missing Behavior`, and `Operational Consequence`.
- For stress/outcome queries, require `Expected Outcome`, `Cause`, and `Evidence Anchor`.
- For interaction queries, require a concise phase order before any caveat about missing integration.

This should be test-driven in `tests/unit/test_answer_contract_naming_guard.py` before touching generation behavior.

## Focused Rerun Result

The focused rerun was executed after adding the answer-shape fix.

Generation artifacts:

- Query 16: `eval/runs/ccg_stage2_agentic_ro3_answer_contract_probe/responses.jsonl`, run `8d3d620b-a157-4e00-8bbf-e7d2332d3bf1`
- Query 18: `eval/runs/ccg_stage2_agentic_ro3_answer_contract_probe_v2/responses.jsonl`, run `b746659f-96d5-420b-bb4d-7d3bae528379`
- Query 20: `eval/runs/ccg_stage2_agentic_ro3_answer_contract_probe_v2/responses.jsonl`, run `aa73ce8a-dea5-44eb-9015-23244489d941`
- Combined judge input: `eval/runs/ccg_stage2_agentic_ro3_answer_contract_probe_v2/responses_combined_q16_q18_q20.jsonl`

Gemini judge result:

```powershell
.\.venv\Scripts\python.exe eval/run_judge.py --responses eval/runs/ccg_stage2_agentic_ro3_answer_contract_probe_v2/responses_combined_q16_q18_q20.jsonl --baseline eval/cursor_baseline.json --judge-config eval/judge_config.json --provider gemini --rpm 2 --output eval/runs/ccg_stage2_agentic_ro3_answer_contract_probe_v2/judge_results__gemini_combined.jsonl
```

Outcome:

- Query 16: improved
- Query 18: improved
- Query 20: improved
- Candidate win rate on focused regression set: 100% improved, 0 regressions, 0 equal

Caveats:

- This is a focused regression validation, not a full promotion run.
- Cerebras judge was unreliable for this step because repeated `429` / queue errors blocked complete judging. Gemini was used as the practical judge provider.
- A full 20-query canary is still required before promotion.

## Decision

Read-only orchestration should not be promoted from only this focused result.

The targeted answer-shape fix resolved the known Q16/Q18/Q20 regression set under Gemini judging. The next correct action is a full canary run before any write/execute mode work.
