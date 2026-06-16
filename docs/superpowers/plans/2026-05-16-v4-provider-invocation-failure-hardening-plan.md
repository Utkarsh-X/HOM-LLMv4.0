# V4 Provider Invocation Failure Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make provider transport/invocation failures retryable and deterministically visible in real-index suite summaries without relying on live network instability.

**Architecture:** Keep provider JSON parsing failures separate from provider invocation failures. Invocation failures happen before any provider response exists, so they should be structured as `provider_invocation_failed`, marked retryable, and propagated through the existing suite metrics/error-code aggregation path.

**Tech Stack:** HOM-LLM v4 provider proposer, real-index provider patch suite, pytest.

---

### Task 1: Retryable Provider Invocation Failure Contract

**Files:**
- Modify: `src/homllm_v4/planning/provider_edit_proposer.py`
- Test: `tests/unit/v4/test_provider_edit_proposer.py`

- [x] **Step 1: Tighten the existing invocation failure test**

Update `test_provider_backed_edit_proposer_reports_provider_invocation_failure` to assert:

```python
assert result.error.retryable is True
```

- [x] **Step 2: Run test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py::test_provider_backed_edit_proposer_reports_provider_invocation_failure -q
```

Expected before implementation: fail because `_failed` currently marks all provider errors `retryable=False`.

- [x] **Step 3: Mark invocation failures retryable**

Change `_failed` so `retryable=True` when `code == "provider_invocation_failed"` and remains `False` for invalid/truncated provider responses.

- [x] **Step 4: Run test and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py::test_provider_backed_edit_proposer_reports_provider_invocation_failure -q
```

Expected: pass.

### Task 2: Deterministic Suite Visibility

**Files:**
- Test: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [x] **Step 1: Add suite-level provider invocation failure test**

Add a test where injected live provider builder returns a provider whose `propose_edit` raises `OSError("dns lookup failed")`. Run `run_real_index_provider_patch_suite` on one no-op case in live mode and assert:

```python
assert result.failed_cases == 1
assert result.case_results[0].error_code == "provider_invocation_failed"
assert result.summary_metrics["error_code_counts"] == {"provider_invocation_failed": 1}
assert result.summary_metrics["numeric_metric_totals"]["provider_tokens_in"] == 0
assert result.summary_metrics["numeric_metric_totals"]["provider_tokens_out"] == 0
```

- [x] **Step 2: Run suite test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_surfaces_provider_invocation_failure -q
```

Expected: pass if the previous provider proposer work already propagates the code correctly; if it fails, fix only the propagation path.

### Task 3: Verify And Record

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify: `docs/superpowers/plans/2026-05-16-v4-provider-invocation-failure-hardening-plan.md`

- [x] **Step 1: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py tests\unit\v4\test_real_index_provider_patch_suite.py -q
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

Expected: v4/full unit suites pass, compileall passes, boundary scan prints no matches.

- [x] **Step 3: Update audits**

Record that provider invocation failures are now retryable and deterministically covered in real-index suite summaries.
