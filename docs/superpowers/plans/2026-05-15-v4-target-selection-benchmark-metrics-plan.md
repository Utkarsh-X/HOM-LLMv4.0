# V4 Target Selection Benchmark Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose provider-planner target-selection telemetry in real-index benchmark case metrics so CLI summaries and persisted evaluation results reveal supplied-target vs evidence-selected coverage.

**Architecture:** Do not change the evaluation harness. `run_real_index_provider_patch_suite` already owns provider-planner results and case metrics; it will copy a small allowlisted subset of `plan_result.telemetry.output_summary` into `CaseExecutionResult.metrics`.

**Tech Stack:** Python, pytest, HOM-LLM v4 evaluation harness, `ProviderProposedPatchPlanner` telemetry.

---

### Task 1: Add Failing Metrics Assertions

**Files:**
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [ ] **Step 1: Assert target-selection metrics on selected case**

In the existing multi-case test, after `selection_case` is found, add:

```python
    assert selection_case.metrics["target_selection_decision"] == "selected"
    assert selection_case.metrics["resolved_target_file"] == "utils/string_tools.py"
```

- [ ] **Step 2: Assert supplied-target metrics on no-op case**

After `noop_case` is found, add:

```python
    assert noop_case.metrics["target_selection_decision"] == "supplied"
    assert noop_case.metrics["resolved_target_file"] == "api/routes.py"
```

- [ ] **Step 3: Run test to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_runs_multiple_cases_with_injected_planner -q
```

Expected: FAIL because case metrics do not yet include target-selection telemetry.

### Task 2: Thread Planner Telemetry into Case Metrics

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`

- [ ] **Step 1: Add planner metric extraction helper**

Add:

```python
def _planner_metrics(plan_result) -> dict[str, object]:
    if plan_result.telemetry is None:
        return {}
    output = plan_result.telemetry.output_summary
    metrics: dict[str, object] = {}
    for key in (
        "target_selection_decision",
        "resolved_target_file",
        "target_selection_confidence",
    ):
        if key in output:
            metrics[key] = output[key]
    if "candidate_file_scores" in output:
        metrics["candidate_file_score_count"] = len(output["candidate_file_scores"])
    return metrics
```

- [ ] **Step 2: Pass planner metrics into `_case_result`**

In the `patch_failed` branch and final success/failure branch, pass:

```python
                planner_metrics=_planner_metrics(plan_result),
```

- [ ] **Step 3: Extend `_case_result`**

Add parameter:

```python
    planner_metrics: dict[str, object] | None = None,
```

Build metrics dict first, then merge:

```python
    metrics = {...}
    metrics.update(planner_metrics or {})
    return CaseExecutionResult(..., metrics=metrics)
```

- [ ] **Step 4: Run real-index suite tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: all tests pass.

### Task 3: Verify CLI and Full Gates

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Run target-selection CLI case**

Run the one-case `eval-real-index-provider-patch --case-id string-truncate-guard-target-selection` command.

Expected: JSON summary still passes. Inspect `evaluation/summary.json` to confirm case metrics include `target_selection_decision: selected`.

- [ ] **Step 2: Run full gates**

Run v4 tests, full unit tests, compileall, and forbidden v3 import scan.

- [ ] **Step 3: Update audits**

Record that benchmark case metrics expose target-selection decisions and resolved target files.
