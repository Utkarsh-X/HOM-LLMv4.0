# V4 Categorical Summary Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggregate string and boolean case metrics in evaluation `summary_metrics` so CLI JSON can show counts for categorical signals such as target-selection decisions.

**Architecture:** Extend `V4EvaluationHarness._summary_metrics` only. Numeric metrics continue using totals/averages. String and boolean metrics get counted under `categorical_metric_counts` as `{metric_name: {metric_value: count}}`. This is generic and does not special-case target selection.

**Tech Stack:** Python, pytest, HOM-LLM v4 evaluation harness.

---

### Task 1: Add Failing Harness Test

**Files:**
- Modify: `tests/unit/v4/test_evaluation_harness.py`

- [ ] **Step 1: Add categorical metrics to run-level metric test**

In `test_evaluation_harness_records_run_level_metric_summary`, extend runner metrics:

```python
                    "target_selection_decision": case.input_payload["target_selection_decision"],
                    "used_baseline": case.input_payload["used_baseline"],
```

Extend case payloads:

```python
                input_payload={
                    "stop_reason": "verified",
                    "duration_ms": 10,
                    "token_count": 100,
                    "target_selection_decision": "selected",
                    "used_baseline": True,
                },
```

and:

```python
                input_payload={
                    "stop_reason": "patch_failed",
                    "duration_ms": 30,
                    "token_count": 20,
                    "target_selection_decision": "supplied",
                    "used_baseline": False,
                },
```

Add assertions:

```python
    assert result.summary_metrics["categorical_metric_counts"] == {
        "target_selection_decision": {"selected": 1, "supplied": 1},
        "used_baseline": {"False": 1, "True": 1},
    }
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_evaluation_harness.py::test_evaluation_harness_records_run_level_metric_summary -q
```

Expected: FAIL because `categorical_metric_counts` does not exist.

### Task 2: Implement Categorical Counts

**Files:**
- Modify: `src/homllm_v4/evaluation/harness.py`

- [ ] **Step 1: Add count dictionary**

Inside `_summary_metrics`, add:

```python
        categorical_counts: dict[str, dict[str, int]] = {}
```

- [ ] **Step 2: Count string and boolean metrics**

Inside the metric loop after numeric handling:

```python
                elif isinstance(value, (str, bool)):
                    value_key = str(value)
                    metric_counts = categorical_counts.setdefault(key, {})
                    metric_counts[value_key] = metric_counts.get(value_key, 0) + 1
```

Important: use `elif` because `bool` is a subclass of `int`.

- [ ] **Step 3: Return sorted categorical counts**

Add to summary:

```python
            "categorical_metric_counts": {
                key: dict(sorted(values.items()))
                for key, values in sorted(categorical_counts.items())
            },
```

- [ ] **Step 4: Run harness tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_evaluation_harness.py -q
```

Expected: all harness tests pass.

### Task 3: Verify CLI Target-Selection Summary

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Run target-selection CLI case**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_categorical_metrics --artifact-root temp\v4_real_index_provider_patch_runs_categorical_metrics --run-id real-index-provider-patch-categorical-metrics-check --case-id string-truncate-guard-target-selection --smoke-safe
```

Expected: top-level CLI JSON includes:

```json
"categorical_metric_counts": {
  "resolved_target_file": {"utils/string_tools.py": 1},
  "target_selection_decision": {"selected": 1}
}
```

- [ ] **Step 2: Run full gates**

Run v4 tests, full unit tests, compileall, and forbidden v3 import scan.

- [ ] **Step 3: Update audits**

Record that categorical metric counts make target-selection coverage visible in top-level CLI summaries.
