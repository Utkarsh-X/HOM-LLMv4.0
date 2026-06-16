# v4 Real-Index More Target Selection Cases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand target-omitted real-index provider patch coverage from three to five cases by adding target-selection variants for `parse-date-strip` and `job-queue-total-size-guard`.

**Architecture:** Reuse the existing deterministic target selection path in `ProviderProposedPatchPlanner`. Add two benchmark cases with `planner_target_file=None`; no selector logic or runtime authority changes unless tests reveal a real ambiguity.

**Tech Stack:** Python, pytest, existing `eval-real-index-provider-patch` CLI/API.

---

## File Structure

- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
  - Add `parse-date-strip-target-selection`.
  - Add `job-queue-total-size-guard-target-selection`.
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`
  - Assert the new target-selection cases verify and resolve to `utils/date_helpers.py` and `async_jobs/job_queue.py`.
  - Assert top-level target-selection counts become `selected=5`, `supplied=8`.
- Modify after verification: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - Record expanded target-omitted coverage.
- Modify after verification: `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Record target-omitted coverage increase and remaining limitations.

---

### Task 1: Red Test For Target-Selection Expansion

**Files:**
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [ ] **Step 1: Add new target-selection assertions**

In `test_real_index_provider_patch_suite_runs_multiple_cases_with_injected_planner`, assert:

```python
date_selection_case = next(
    case for case in result.case_results if case.case_id == "parse-date-strip-target-selection"
)
assert date_selection_case.actual_stop_reason == "verified"
assert date_selection_case.metrics["target_selection_decision"] == "selected"
assert date_selection_case.metrics["resolved_target_file"] == "utils/date_helpers.py"
job_selection_case = next(
    case for case in result.case_results if case.case_id == "job-queue-total-size-guard-target-selection"
)
assert job_selection_case.actual_stop_reason == "verified"
assert job_selection_case.metrics["target_selection_decision"] == "selected"
assert job_selection_case.metrics["resolved_target_file"] == "async_jobs/job_queue.py"
assert result.summary_metrics["categorical_metric_counts"]["target_selection_decision"] == {
    "selected": 5,
    "supplied": 8,
}
assert result.summary_metrics["baseline_case_count"] == 10
```

- [ ] **Step 2: Run the targeted test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_runs_multiple_cases_with_injected_planner -q
```

Expected: failure because the two new target-selection cases do not exist yet.

---

### Task 2: Add Target-Omitted Benchmark Cases

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`

- [ ] **Step 1: Add `parse-date-strip-target-selection`**

Add:

```python
RealIndexProviderPatchCase(
    case_id="parse-date-strip-target-selection",
    target_file="utils/date_helpers.py",
    query="utils date_helpers parse_date strip whitespace before datetime parsing",
    intent="Make parse_date tolerate leading and trailing whitespace before parsing.",
    expected_behavior="parse_date(' 2024-01-02 ') returns a datetime and parse_date('bad') returns None.",
    provider_mode="parse_date_strip",
    verification_mode="parse_date_strip",
    planner_target_file=None,
),
```

- [ ] **Step 2: Add `job-queue-total-size-guard-target-selection`**

Add:

```python
RealIndexProviderPatchCase(
    case_id="job-queue-total-size-guard-target-selection",
    target_file="async_jobs/job_queue.py",
    query="async_jobs job_queue enqueue max_queue_size total pending jobs guard",
    intent="Make JobQueue enforce max_queue_size using total queued jobs, not priority bucket count.",
    expected_behavior="A queue with max_queue_size=2 rejects the third queued job.",
    provider_mode="job_queue_size_guard",
    verification_mode="job_queue_size_guard",
    planner_target_file=None,
),
```

- [ ] **Step 3: Run targeted test and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_runs_multiple_cases_with_injected_planner -q
```

Expected:
- test passes;
- target-selection cases resolve correctly.

If either case stops with `target_selection_ambiguous`, do not tune blindly. Inspect candidate scores first and only adjust query text or selector logic with a new failing unit test if the ambiguity is genuinely caused by weak lexical signal.

---

### Task 3: Full Verification And Audit Update

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Run real-index suite tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: all real-index provider suite tests pass.

- [ ] **Step 2: Run v4 and full unit suites**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
```

Expected: both pass.

- [ ] **Step 3: Run compile and boundary checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected: compile exits `0`; boundary scan has no output.

- [ ] **Step 4: Run CLI benchmark**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_more_target_selection --artifact-root temp\v4_real_index_provider_patch_runs_more_target_selection --run-id real-index-provider-patch-more-target-selection-check --smoke-safe
```

Expected:
- `passed_cases=13`
- `failed_cases=0`
- `baseline_case_count=10`
- `target_selection_decision={"selected":5,"supplied":8}`
- `stop_reason_counts={"verified":13}`

- [ ] **Step 5: Update audits**

Record:
- real-index benchmark has 13 cases;
- behavior baselines increased to 10;
- target-omitted coverage increased to five cases across `string_tools`, `validators`, `date_helpers`, and `job_queue`.

---

## Self-Review

Spec coverage:
- This plan directly improves target-localization validation without requiring live provider calls.
- It uses existing runtime paths and does not broaden tool authority.

Placeholder scan:
- No placeholders or deferred implementation steps are present.

Type consistency:
- New target-selection cases reuse existing `provider_mode`, `verification_mode`, and `planner_target_file=None` behavior.
