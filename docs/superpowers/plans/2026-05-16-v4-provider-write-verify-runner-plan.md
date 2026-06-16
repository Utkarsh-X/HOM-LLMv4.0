# V4 Provider Write-Verify Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract bounded provider repair orchestration from the real-index evaluation suite into a reusable runtime runner.

**Architecture:** Keep `WriteVerifyLoop` deterministic and provider-unaware. Add `ProviderWriteVerifyRunner` as the layer that connects `ProviderProposedPatchPlanner` to `WriteVerifyLoop`, handles one or more repair planning attempts after verification failure/timeout, builds repair context, and aggregates provider/planner metrics. The real-index evaluation suite should call this runner instead of owning repair orchestration directly.

**Tech Stack:** HOM-LLM v4 runtime dataclasses, provider patch planner contracts, write-verify loop, pytest.

---

### Task 1: Add Reusable Provider Write-Verify Runner

**Files:**
- Create: `src/homllm_v4/runtime/provider_write_verify_runner.py`
- Test: `tests/unit/v4/test_provider_write_verify_runner.py`

- [x] **Step 1: Write failing repair-success runner test**

Create `tests/unit/v4/test_provider_write_verify_runner.py` with a fake planner and real `WriteVerifyLoop`. The fake planner returns an initial patch that fails verification, then a repair patch that passes after receiving repair context. Assert:

```python
assert result.stop_reason == "verified"
assert result.patch_attempt_count == 2
assert result.provider_repair_attempt_count == 1
assert result.planner_metrics["provider_tokens_in"] == 203
assert "Previous verification stopped with reason verification_failed" in planner.repair_contexts[0]
```

- [x] **Step 2: Run runner test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_write_verify_runner.py::test_provider_write_verify_runner_repairs_after_verification_failure -q
```

Expected before implementation: import failure for `ProviderWriteVerifyRunner`.

- [x] **Step 3: Implement runner**

Create `ProviderWriteVerifyRunRequest`, `ProviderWriteVerifyRunResult`, and `ProviderWriteVerifyRunner`. The runner must:

- call `planner.plan(plan_request)`
- run `WriteVerifyLoop` once for a successful plan
- retry planning only when stop reason is `verification_failed` or `verification_timeout`
- pass `repair_context` by replacing the immutable `ProviderProposedPatchPlanRequest`
- aggregate provider token/prompt metrics across plan attempts
- return `patch_failed` with planner error code when planning fails

- [x] **Step 4: Run runner test and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_write_verify_runner.py::test_provider_write_verify_runner_repairs_after_verification_failure -q
```

Expected: pass.

- [x] **Step 5: Add planner-failure runner test**

Add a test where the fake planner returns a failed `CapabilityResult` with error code `provider_invocation_failed`. Assert the runner returns `stop_reason="patch_failed"`, `error_code="provider_invocation_failed"`, zero patch attempts, and zero verification results.

- [x] **Step 6: Run planner-failure runner test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_write_verify_runner.py::test_provider_write_verify_runner_surfaces_planner_failure -q
```

Expected: pass.

### Task 2: Refactor Real-Index Suite To Use Runner

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
- Test: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [x] **Step 1: Refactor suite run_case**

Replace local repair orchestration in `run_case` with `ProviderWriteVerifyRunner(...).run(...)`.

- [x] **Step 2: Remove duplicate helper functions**

Remove `_combined_planner_metrics`, `_repair_context`, and `_truncate_diagnostic` from `real_index_provider_suites.py` if no longer used.

- [x] **Step 3: Run real-index suite repair tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_repairs_after_verification_failure tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_surfaces_provider_invocation_failure -q
```

Expected: both pass.

### Task 3: Verify And Record

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify: `docs/superpowers/plans/2026-05-16-v4-provider-write-verify-runner-plan.md`

- [x] **Step 1: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_write_verify_runner.py tests\unit\v4\test_provider_edit_proposer.py tests\unit\v4\test_provider_patch_planner.py tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_real_index_provider_patch_suite.py -q
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

Record that bounded provider repair is now a reusable runtime runner used by the real-index suite, not benchmark-only code.
