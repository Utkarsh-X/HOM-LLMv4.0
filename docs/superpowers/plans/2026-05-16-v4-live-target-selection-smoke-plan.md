# V4 Live Target Selection Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate the live provider path when `target_file` is omitted and v4 must use real indexed retrieval plus deterministic target selection before live patch synthesis.

**Architecture:** Use the existing `eval-real-index-provider-patch` CLI with `gemini-3.1-flash-lite-preview`, copied workspaces, prompt cap, output-token cap, and one case per run. This exercises retrieval, target selection, direct read, evidence-context prompt assembly, provider patch proposal, patch application, verification, and artifact persistence.

**Tech Stack:** HOM-LLM v4 CLI, v3 real-index adapter, Gemini provider, copied `test_repo` workspaces.

---

### Task 1: Live Target-Omitted Semantic Smokes

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [x] **Step 1: Run string truncate target-selection live smoke**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_string_truncate_target --artifact-root temp\v4_real_index_provider_patch_runs_live_string_truncate_target --run-id real-index-provider-patch-live-string-truncate-target-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id string-truncate-guard-target-selection --max-prompt-chars 15000 --smoke-safe
```

Expected: `passed_cases=1`, `target_selection_decision=selected`, `resolved_target_file=utils/string_tools.py`.

- [x] **Step 2: Run file-path validator target-selection live smoke**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_file_path_target --artifact-root temp\v4_real_index_provider_patch_runs_live_file_path_target --run-id real-index-provider-patch-live-file-path-target-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id validate-file-path-drive-guard-target-selection --max-prompt-chars 15000 --smoke-safe
```

Expected: `passed_cases=1`, `target_selection_decision=selected`, `resolved_target_file=utils/validators.py`.

- [x] **Step 3: Run email validator target-selection live smoke**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_email_target --artifact-root temp\v4_real_index_provider_patch_runs_live_email_target --run-id real-index-provider-patch-live-email-target-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id validate-email-local-dot-guard-target-selection --max-prompt-chars 15000 --smoke-safe
```

Expected: `passed_cases=1`, `target_selection_decision=selected`, `resolved_target_file=utils/validators.py`.

- [x] **Step 4: Inspect persisted artifacts**

For each successful run, inspect `evaluation/summary.json`, `provider/<case>/response.txt`, and `response/write_verify_loop_result.json`.

Confirm:

```text
actual_stop_reason=verified
baseline_stop_reason=verification_failed
verification exit_code=0
patch diff is target-file scoped
```

- [x] **Step 5: Update audit docs**

Record the live target-selection smoke results and remaining limitations in both audit docs.

- [x] **Step 6: Run relevant verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py tests\unit\v4\test_provider_patch_planner.py tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: provider-related unit tests still pass.
