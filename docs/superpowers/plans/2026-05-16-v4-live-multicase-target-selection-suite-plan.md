# V4 Live Multicase Target Selection Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate that the live provider path works as a single multi-case suite for target-omitted real-index patch tasks, not only as isolated one-case smokes.

**Architecture:** Reuse the existing `eval-real-index-provider-patch` CLI with repeated `--case-id` arguments, copied workspaces, prompt caps, output-token caps, and Gemini live provider mode. This exercises run-level aggregation across retrieval, target selection, provider patch proposal, patch application, verification, baseline comparison, and artifact persistence for three semantic target-omitted cases.

**Tech Stack:** HOM-LLM v4 CLI, v3 real-index adapter, Gemini provider, copied `test_repo` workspaces, existing provider-related unit tests.

---

### Task 1: Run Three-Case Live Target-Selection Suite

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify: `docs/superpowers/plans/2026-05-16-v4-live-multicase-target-selection-suite-plan.md`

- [x] **Step 1: Run the live three-case target-selection suite**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_target_multicase --artifact-root temp\v4_real_index_provider_patch_runs_live_target_multicase --run-id real-index-provider-patch-live-target-multicase-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id string-truncate-guard-target-selection --case-id validate-file-path-drive-guard-target-selection --case-id validate-email-local-dot-guard-target-selection --max-prompt-chars 15000 --smoke-safe
```

Expected: exit code `0`, `total_cases=3`, `passed_cases=3`, `failed_cases=0`, `baseline_case_count=3`, `stop_reason_counts={"verified":3}`, `target_selection_decision={"selected":3}`, and resolved targets covering `utils/string_tools.py` and `utils/validators.py`.

- [x] **Step 2: Inspect persisted run summary**

Run:

```powershell
Get-Content -Raw -Path temp\v4_real_index_provider_patch_runs_live_target_multicase\real-index-provider-patch-live-target-multicase-check\evaluation\summary.json
```

Expected: `case_results` contains the three selected case IDs, each with `actual_stop_reason="verified"`, `baseline_stop_reason="verification_failed"`, `provider_tokens_in > 0`, `provider_tokens_out > 0`, `prompt_char_count > 0`, and `verification_count=1`.

- [x] **Step 3: Update audit docs**

Record the multi-case live suite result in both audit docs and keep the remaining limitations honest: this removes the "no multi-case live provider benchmark" gap for the three-case target-selection slice, but does not establish broad production readiness or external-baseline superiority.

- [x] **Step 4: Run focused verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py tests\unit\v4\test_provider_patch_planner.py tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: `32 passed`.
