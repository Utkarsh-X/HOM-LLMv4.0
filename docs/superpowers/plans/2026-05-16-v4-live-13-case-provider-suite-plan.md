# V4 Live 13-Case Provider Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the full current 13-case real-index provider patch suite with a live Gemini provider, repair enabled, and bounded prompt/output budgets.

**Architecture:** Reuse the existing `eval-real-index-provider-patch` CLI and copied-workspace evaluation harness. Do not add runtime authority. Treat any failure as benchmark evidence first, not as an automatic reason to change runtime behavior.

**Tech Stack:** HOM-LLM v4 CLI, Gemini live provider adapter, real-index provider patch suite, copied test workspaces, existing v4 verification commands.

---

### Task 1: Run Full Live Suite

**Files:**
- Read: `src/homllm_v4/evaluation/real_index_provider_suites.py`
- Read: `runtime/v4_cli.py`
- Modify only for evidence recording: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify only for evidence recording: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`

- [x] **Step 1: Run the 13-case live preview suite**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_full13_preview --artifact-root temp\v4_real_index_provider_patch_runs_live_full13_preview --run-id real-index-provider-patch-live-full13-preview-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --max-prompt-chars 22000 --provider-repair-attempts 1 --smoke-safe
```

Expected useful outcomes:

- Best case: exit code `0`, `13 passed_cases`, `0 failed_cases`, broad `resolved_target_file` coverage, and run-level token/prompt metrics.
- Acceptable partial outcome: structured JSON with failed cases and existing `stop_reason_counts` / `error_code_counts`; record exact failure classes and do not overclaim.
- If provider/network fails, record `provider_invocation_failed` evidence and stop this slice.

### Task 2: Record Evidence

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/superpowers/plans/2026-05-16-v4-live-13-case-provider-suite-plan.md`

- [x] **Step 1: Update audits with exact suite result**

Record:

- exit code class
- passed/failed/total cases
- `baseline_case_count`
- `stop_reason_counts`
- `error_code_counts`
- `target_selection_decision`
- `resolved_target_file`
- `provider_tokens_in`, `provider_tokens_out`, `prompt_char_count`
- `provider_repair_attempt_count`
- whether live repair was exercised

- [x] **Step 2: Run verification only if code changed**

If this slice only updates docs, no unit test rerun is required. If code changes, run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_write_verify_runner.py tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_provider_edit_proposer.py tests\unit\v4\test_provider_patch_planner.py -q
```

Expected: pass.
