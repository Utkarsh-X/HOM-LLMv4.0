# V4 Live Expanded Target Selection Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand live target-omitted real-index patch synthesis beyond the initial three utility cases by running the two remaining target-selection semantic cases.

**Architecture:** Use the existing `eval-real-index-provider-patch` CLI with repeated `--case-id` arguments and Gemini live provider mode. This keeps runtime authority unchanged while testing whether retrieval, deterministic target selection, evidence prompts, provider synthesis, patching, and verification hold for `utils/date_helpers.py` and `async_jobs/job_queue.py`.

**Tech Stack:** HOM-LLM v4 CLI, v3 real-index adapter, Gemini provider, copied `test_repo` workspaces, existing provider-focused unit tests.

---

### Task 1: Run Remaining Target-Omitted Live Cases

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify: `docs/superpowers/plans/2026-05-16-v4-live-expanded-target-selection-suite-plan.md`

- [x] **Step 1: Run the two-case live expanded target-selection suite**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_target_expanded --artifact-root temp\v4_real_index_provider_patch_runs_live_target_expanded --run-id real-index-provider-patch-live-target-expanded-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id parse-date-strip-target-selection --case-id job-queue-total-size-guard-target-selection --max-prompt-chars 15000 --smoke-safe
```

Expected if the live provider succeeds: exit code `0`, `total_cases=2`, `passed_cases=2`, `failed_cases=0`, `baseline_case_count=2`, `stop_reason_counts={"verified":2}`, `target_selection_decision={"selected":2}`, and resolved targets covering `utils/date_helpers.py` and `async_jobs/job_queue.py`.

Expected if the live provider fails: preserve the structured JSON/artifacts, do not hide the failure, and update the audit with the actual failure class before deciding on a repair-loop or prompt-contract follow-up.

Observed:

- The first `15000` cap run returned `1 passed_cases`, `1 failed_cases`, and `provider_prompt_budget_exceeded` for `job-queue-total-size-guard-target-selection`.
- A single-case `22000` cap rerun invoked the provider but timed out verification because the generated patch called `self.get_queue_size()` from inside `with self._lock:`.
- After adding a prompt lock-safety instruction and a job-queue expected-behavior constraint, the single job-queue case passed with `provider_tokens_in=5435.0`, `provider_tokens_out=2863.0`, and `stop_reason_counts={"verified":1}`.
- The final `22000` cap five-case target-omitted suite passed with `5 passed_cases`, `0 failed_cases`, `target_selection_decision={"selected":5}`, and `stop_reason_counts={"verified":5}`.

- [x] **Step 2: Inspect persisted run summary**

Run:

```powershell
Get-Content -Raw -Path temp\v4_real_index_provider_patch_runs_live_target_expanded\real-index-provider-patch-live-target-expanded-check\evaluation\summary.json
```

Expected: each case result records `actual_stop_reason`, `baseline_stop_reason`, `target_selection_decision`, `resolved_target_file`, prompt metrics, provider token metrics, and verification metrics.

- [x] **Step 3: Update audit docs**

Record the expanded live target-selection result in both audit docs. If the suite passes, state that all five target-omitted real-index semantic cases have now been exercised live at least once. If it fails, state the exact failing case and structured failure mode.

- [x] **Step 4: Run focused verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py tests\unit\v4\test_provider_patch_planner.py tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: `32 passed`.
