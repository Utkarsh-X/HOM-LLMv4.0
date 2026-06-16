# V4 Expanded 15-Case Quality Validation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate the expanded 15-case real-index provider patch suite after adding hard evidence-value cases and quality-dimension metrics.

**Architecture:** Do not change runtime behavior. Run the existing CLI in fake, live retrieval/evidence, and live direct-provider target-known modes. Interpret results quality-first: pass rate, localization, verification kind, target knowledge, and safety/error classes before token totals.

**Tech Stack:** HOM-LLM v4 CLI, real-index provider patch suite, Gemini live provider adapter, copied workspaces.

---

### Task 1: Run Expanded Fake Suite

**Files:**
- Modify only for evidence recording: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify only for evidence recording: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`

- [x] **Step 1: Run full fake 15-case suite**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_quality_full15_fake --artifact-root temp\v4_real_index_provider_patch_runs_quality_full15_fake --run-id real-index-provider-patch-quality-full15-fake-check --smoke-safe
```

Expected: `15 passed_cases`, `0 failed_cases`, visible quality categorical metrics.

### Task 2: Run Expanded Live Retrieval Suite

**Files:**
- Modify only for evidence recording: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify only for evidence recording: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`

- [x] **Step 1: Run full live retrieval/evidence 15-case suite**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_quality_full15_live --artifact-root temp\v4_real_index_provider_patch_runs_quality_full15_live --run-id real-index-provider-patch-quality-full15-live-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --max-prompt-chars 22000 --provider-repair-attempts 1 --smoke-safe
```

Expected useful outcome: record pass/fail, quality categories, target-selection counts, provider tokens, prompt totals, and repair count.

Actual result, 2026-05-17 fresh run `real-index-provider-patch-quality-full15-live-check-20260517a`: `14 passed_cases`, `1 failed_case`, `baseline_case_count=12`, `stop_reason_counts={"verified":14,"patch_failed":1}`, and `error_code_counts={"provider_invocation_failed":1}`. The failed case was `validate-file-path-drive-guard-target-selection` and the failure was a provider/server disconnect before patch verification, not a localization or verification failure. Quality counts were `quality_requires_localization={"False":8,"True":7}`, `quality_verification_kind={"behavior":12,"compile":3}`, `quality_baseline_target_knowledge={"retrieval_localizes":15}`, `target_selection_decision={"selected":6,"supplied":8}`, `provider_tokens_in=48101.0`, `provider_tokens_out=25438.0`, `prompt_char_count=172065.0`, and `provider_repair_attempt_count=0.0`.

### Task 3: Run Expanded Live Direct-Provider Baseline

**Files:**
- Modify only for evidence recording: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify only for evidence recording: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`

- [x] **Step 1: Run full live direct-provider target-known 15-case suite**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_quality_full15_direct_live --artifact-root temp\v4_real_index_provider_patch_runs_quality_full15_direct_live --run-id real-index-provider-patch-quality-full15-direct-live-check --planner-context-mode direct-provider --direct-provider-target-source actual --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --max-prompt-chars 22000 --provider-repair-attempts 1 --smoke-safe
```

Expected useful outcome: record pass/fail and quality-category/token comparison against retrieval mode.

Actual result, split over the initial 2026-05-17 full run plus the 2026-05-19 retry after fixing volatile `__pycache__` workspace copies: the initial direct-provider target-known run verified 9 supplied-target cases and exposed a copy-materialization bug on the six target-selection cases; the fresh six-case retry `real-index-provider-patch-quality-full15-direct-live-retry-20260519a` then passed `6/6`. Effective direct-provider target-known evidence is therefore `15/15 verified` across split artifacts, `baseline_case_count=12`, `target_selection_decision={"direct_supplied":15}`, `planner_context_mode={"direct_provider":15}`, `quality_baseline_target_knowledge={"target_known":15}`, `quality_requires_localization={"False":8,"True":7}`, `quality_verification_kind={"behavior":12,"compile":3}`, `provider_tokens_in=27892.0`, `provider_tokens_out=25778.0`, `prompt_char_count=103753.0`, and `provider_repair_attempt_count=0.0`. This is not a localization baseline because it gives the provider the target file.

### Task 4: Record Comparison

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/superpowers/plans/2026-05-16-v4-expanded-15-case-quality-validation-plan.md`

- [x] **Step 1: Update audits**

Record:

- fake 15-case result
- live retrieval 15-case result
- live direct-provider target-known 15-case result
- pass-rate comparison
- quality categorical counts
- whether repair was exercised
- interpretation that target-known direct-provider is not a localization baseline

- [x] **Step 2: Mark plan complete**

Focused and broader checks were run because this slice fixed the discovered workspace-copy bug: `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_evaluation_harness.py -q` passed with `22 passed`; `.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q` passed with `181 passed, 6 skipped`; and `.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py` passed.
