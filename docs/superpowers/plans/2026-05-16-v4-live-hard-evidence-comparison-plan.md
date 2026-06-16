# V4 Live Hard Evidence Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the two harder target-omitted evidence-value cases live with Gemini preview, then run the same cases with direct-provider baseline mode.

**Architecture:** Do not change runtime behavior. Use existing `eval-real-index-provider-patch` CLI with case filters, copied workspaces, prompt/output caps, and repair enabled. Record the comparison honestly: retrieval mode tests localization and evidence context; direct-provider mode is target-known and tests only synthesis with no retrieved evidence context.

**Tech Stack:** HOM-LLM v4 CLI, Gemini live provider adapter, real-index provider patch suite, direct-provider baseline mode.

---

### Task 1: Run Live Retrieval/Evidence Hard Cases

**Files:**
- Modify only for evidence recording: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify only for evidence recording: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`

- [x] **Step 1: Run live retrieval-mode hard cases**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_hard_evidence_live --artifact-root temp\v4_real_index_provider_patch_runs_hard_evidence_live --run-id real-index-provider-patch-hard-evidence-live-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --max-prompt-chars 22000 --provider-repair-attempts 1 --case-id cache-namespace-invalidate-target-selection --case-id metrics-labelled-stats-target-selection --smoke-safe
```

Expected useful outcome: record pass/fail, selected target files, prompt/token totals, and repair count.

### Task 2: Run Live Direct-Provider Baseline

**Files:**
- Modify only for evidence recording: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify only for evidence recording: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`

- [x] **Step 1: Run live direct-provider hard-case baseline**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_hard_evidence_direct_live --artifact-root temp\v4_real_index_provider_patch_runs_hard_evidence_direct_live --run-id real-index-provider-patch-hard-evidence-direct-live-check --planner-context-mode direct-provider --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --max-prompt-chars 22000 --provider-repair-attempts 1 --case-id cache-namespace-invalidate-target-selection --case-id metrics-labelled-stats-target-selection --smoke-safe
```

Expected useful outcome: record pass/fail and token totals for the target-known baseline.

### Task 3: Record Comparison

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/superpowers/plans/2026-05-16-v4-live-hard-evidence-comparison-plan.md`

- [x] **Step 1: Update audits**

Record:

- retrieval-mode live hard-case result
- direct-provider live hard-case result
- pass-rate comparison
- token comparison
- whether repair was exercised
- interpretation without overclaiming

- [x] **Step 2: Mark plan complete**

No unit tests are required if only live runs and docs are changed.
