# V4 Live Provider Repair Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Check whether the live Gemini provider path can exercise bounded provider repair through the reusable `ProviderWriteVerifyRunner`.

**Architecture:** Do not expand runtime authority or add new write capabilities. Use the existing `eval-real-index-provider-patch` CLI against copied workspaces, with `--provider-repair-attempts 1`, case-limited execution, prompt caps, output-token caps, and structured result recording. If the live call fails due provider/network instability, preserve the structured failure evidence and do not treat it as runtime success.

**Tech Stack:** HOM-LLM v4 CLI, Gemini live provider adapter, real-index provider patch suite, existing copied-workspace verification harness.

---

### Task 1: Run Live Repair Probe

**Files:**
- Read: `runtime/v4_cli.py`
- Read: `src/homllm_v4/cli.py`
- Modify only if needed: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify only if needed: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`

- [x] **Step 1: Run prompt-safe live repair probe with `gemini-3.1-flash-lite`**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_repair_flash_lite --artifact-root temp\v4_real_index_provider_patch_runs_live_repair_flash_lite --run-id real-index-provider-patch-live-repair-flash-lite-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id string-truncate-guard --max-prompt-chars 15000 --provider-repair-attempts 1 --smoke-safe
```

Expected useful outcomes:

- Best case: exit code `0`, `passed_cases=1`, `provider_repair_attempt_count=1`, and `patch_attempt_count=2`, proving live repair.
- Acceptable non-repair outcome: exit code `0`, `provider_repair_attempt_count=0`; record that the live path passed but repair was not exercised.
- Acceptable failure outcome: structured JSON with `provider_invocation_failed`, `verification_failed`, `verification_timeout`, or another existing error code; record the exact failure without changing runtime behavior prematurely.

- [x] **Step 2: If needed, retry with `gemini-3.1-flash-lite-preview`**

Run only if Step 1 fails due provider/network/model instability or passes without exercising repair:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_repair_flash_lite_preview --artifact-root temp\v4_real_index_provider_patch_runs_live_repair_flash_lite_preview --run-id real-index-provider-patch-live-repair-flash-lite-preview-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id string-truncate-guard --max-prompt-chars 15000 --provider-repair-attempts 1 --smoke-safe
```

Expected useful outcomes are the same as Step 1.

### Task 2: Record Evidence

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/superpowers/plans/2026-05-16-v4-live-provider-repair-probe-plan.md`

- [x] **Step 1: Record live probe result**

Update the audit docs with the exact command result:

- model used
- exit code class
- `passed_cases` / `failed_cases`
- `stop_reason_counts`
- `error_code_counts` if present
- `provider_repair_attempt_count` if present
- whether live repair was actually exercised

- [x] **Step 2: Run focused regression after any code changes**

If no code changed, this step is not required. If code changed, run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_write_verify_runner.py tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_provider_edit_proposer.py tests\unit\v4\test_provider_patch_planner.py -q
```

Expected: pass.
