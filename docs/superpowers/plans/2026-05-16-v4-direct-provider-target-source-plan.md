# V4 Direct Provider Target Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make direct-provider baseline target knowledge explicit, so evaluations can distinguish target-known direct editing from target-unavailable direct editing.

**Architecture:** Keep retrieval mode unchanged. Add `direct_provider_target_source="actual" | "planner"` to `run_real_index_provider_patch_suite`. In direct-provider mode, `"actual"` keeps the current target-known baseline. `"planner"` uses the case planner target; target-omitted cases therefore fail with `direct_provider_target_required`, making the baseline limitation observable instead of hidden.

**Tech Stack:** HOM-LLM v4 evaluation suite, CLI, pytest.

---

### Task 1: Add Suite Target Source Option

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
- Test: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [x] **Step 1: Write failing target-unavailable direct-provider test**

Add a test running `run_real_index_provider_patch_suite(..., planner_context_mode="direct_provider", direct_provider_target_source="planner", case_ids=("cache-namespace-invalidate-target-selection",))`. Assert:

```python
assert result.failed_cases == 1
assert result.case_results[0].error_code == "direct_provider_target_required"
assert result.summary_metrics["error_code_counts"] == {"direct_provider_target_required": 1}
```

- [x] **Step 2: Run test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_direct_provider_planner_target_source_exposes_missing_target_for_target_omitted_case -q
```

Expected before implementation: unexpected keyword argument `direct_provider_target_source`.

- [x] **Step 3: Implement suite option**

Add `direct_provider_target_source: str = "actual"`.

Rules:

- valid values are `"actual"` and `"planner"`
- invalid values raise `ValueError("unsupported_direct_provider_target_source: <value>")`
- only direct-provider mode uses this option
- `"actual"` keeps current behavior
- `"planner"` uses `_evaluation_planner_target_file(case)` without replacing `None`

- [x] **Step 4: Run target-unavailable test and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_direct_provider_planner_target_source_exposes_missing_target_for_target_omitted_case -q
```

Expected: pass.

### Task 2: Add CLI Flag

**Files:**
- Modify: `src/homllm_v4/cli.py`
- Test: `tests/unit/v4/test_provider_fixture_cli.py`

- [x] **Step 1: Write failing CLI propagation test**

Add a CLI test invoking:

```python
main([
    "eval-real-index-provider-patch",
    "--config", "cfg.yaml",
    "--source-workspace-root", "repo",
    "--workspace-root", "work",
    "--artifact-root", "runs",
    "--planner-context-mode", "direct-provider",
    "--direct-provider-target-source", "planner",
])
```

Assert captured suite kwargs include `direct_provider_target_source == "planner"`.

- [x] **Step 2: Run CLI test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_passes_direct_provider_target_source -q
```

Expected before implementation: parser rejects `--direct-provider-target-source`.

- [x] **Step 3: Implement CLI flag**

Add:

```python
real_index_provider_patch.add_argument(
    "--direct-provider-target-source",
    choices=("actual", "planner"),
    default="actual",
)
```

Pass it to normal and prompt-preflight suite calls.

- [x] **Step 4: Run CLI test and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_passes_direct_provider_target_source -q
```

Expected: pass.

### Task 3: Verify And Record

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/superpowers/plans/2026-05-16-v4-direct-provider-target-source-plan.md`

- [x] **Step 1: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_direct_provider_patch_planner.py -q
```

Expected: pass.

- [x] **Step 2: Run broad verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected: pass/no forbidden imports.

- [x] **Step 3: Run target-unavailable direct-provider smoke**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_direct_provider_planner_target --artifact-root temp\v4_real_index_provider_patch_runs_direct_provider_planner_target --run-id real-index-provider-patch-direct-provider-planner-target-check --planner-context-mode direct-provider --direct-provider-target-source planner --case-id cache-namespace-invalidate-target-selection --case-id metrics-labelled-stats-target-selection --smoke-safe
```

Expected: `0 passed_cases`, `2 failed_cases`, `error_code_counts={"direct_provider_target_required":2}`.

- [x] **Step 4: Update audits**

Record that direct-provider target-known and target-unavailable baselines are now separated.
