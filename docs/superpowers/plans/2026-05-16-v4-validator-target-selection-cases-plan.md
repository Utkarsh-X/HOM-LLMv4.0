# V4 Validator Target-Selection Cases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand real-index target-omitted write coverage from one semantic case to three by adding validator behavior cases that rely on evidence-selected target files.

**Architecture:** Reuse the existing real-index provider patch benchmark and fake-provider semantic transformations. Add target-omitted variants for file-path and email validator fixes by setting `planner_target_file=None`, while keeping `target_file` as the expected provider/edit target for fixture setup and verification.

**Tech Stack:** Python, pytest, HOM-LLM v4 real-index provider benchmark, real v3 indexed retrieval smoke via CLI.

---

### Task 1: Add Failing Benchmark Test

**Files:**
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [ ] **Step 1: Make fake broad retrieval choose validators for validator queries**

In `FakeRetrievalService.retrieve`, replace the broad retrieval fallback with:

```python
        if request.target_files:
            target_file = request.target_files[0]
        elif "validate" in request.query or "validator" in request.query:
            target_file = "utils/validators.py"
        else:
            target_file = "utils/string_tools.py"
```

- [ ] **Step 2: Assert the new target-selection cases verify**

In the existing multi-case benchmark test, add:

```python
    file_path_selection_case = next(
        case
        for case in result.case_results
        if case.case_id == "validate-file-path-drive-guard-target-selection"
    )
    assert file_path_selection_case.actual_stop_reason == "verified"
    assert file_path_selection_case.metrics["target_selection_decision"] == "selected"
    assert file_path_selection_case.metrics["resolved_target_file"] == "utils/validators.py"

    email_selection_case = next(
        case
        for case in result.case_results
        if case.case_id == "validate-email-local-dot-guard-target-selection"
    )
    assert email_selection_case.actual_stop_reason == "verified"
    assert email_selection_case.metrics["target_selection_decision"] == "selected"
    assert email_selection_case.metrics["resolved_target_file"] == "utils/validators.py"
```

- [ ] **Step 3: Update expected semantic baseline count**

Change:

```python
    assert result.summary_metrics["baseline_case_count"] == 4
```

to:

```python
    assert result.summary_metrics["baseline_case_count"] == 6
```

- [ ] **Step 4: Run test to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_runs_multiple_cases_with_injected_planner -q
```

Expected: FAIL because the two validator target-selection cases do not exist yet.

### Task 2: Add Validator Target-Selection Cases

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`

- [ ] **Step 1: Add file-path validator target-selection case**

Append a `RealIndexProviderPatchCase`:

```python
    RealIndexProviderPatchCase(
        case_id="validate-file-path-drive-guard-target-selection",
        target_file="utils/validators.py",
        query="utils validators validate_file_path Windows drive absolute path rejection",
        intent="Reject Windows drive-qualified paths in validate_file_path.",
        expected_behavior="validate_file_path('C:/secret.txt') returns invalid.",
        provider_mode="file_path_drive_guard",
        verification_mode="file_path_drive_guard",
        planner_target_file=None,
    ),
```

- [ ] **Step 2: Add email validator target-selection case**

Append:

```python
    RealIndexProviderPatchCase(
        case_id="validate-email-local-dot-guard-target-selection",
        target_file="utils/validators.py",
        query="utils validators validate_email consecutive dots local part rejection",
        intent="Reject email addresses with consecutive dots before @.",
        expected_behavior=(
            "validate_email('a..b@example.com') returns invalid while "
            "validate_email('a.b@example.com') remains valid."
        ),
        provider_mode="email_local_dot_guard",
        verification_mode="email_local_dot_guard",
        planner_target_file=None,
    ),
```

- [ ] **Step 3: Run real-index suite tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: all tests pass.

### Task 3: Verify CLI and Full Gates

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Run focused validator target-selection CLI cases**

Run each new `--case-id` through `eval-real-index-provider-patch`.

Expected: each returns `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`, and top-level `categorical_metric_counts.target_selection_decision.selected=1`.

- [ ] **Step 2: Run full real-index benchmark**

Run the full real-index provider patch CLI with fresh roots.

Expected: all cases pass, baseline count increases to `6`, and categorical target-selection count shows at least `selected: 3`.

- [ ] **Step 3: Run full verification gates**

Run v4 tests, full unit tests, compileall, and forbidden v3 import scan.

- [ ] **Step 4: Update audits**

Record that target-omitted real-index coverage is now three semantic cases, while broader/live synthesis remains incomplete.
