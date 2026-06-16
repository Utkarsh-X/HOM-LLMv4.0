# V4 Real-Index No-Patch Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a no-patch baseline runner to the real-index provider patch benchmark so semantic patch cases compare candidate behavior against an unchanged copied workspace.

**Architecture:** Reuse the existing `V4EvaluationHarness` baseline hook instead of inventing a second result format. Assign `baseline_runner_id="no_patch_baseline"` only to semantic behavior cases where unchanged code is expected to fail, and run verification through the same local restricted command service used by candidate verification.

**Tech Stack:** Python dataclasses, pytest, HOM-LLM v4 evaluation harness, `LocalCommandService`, copied `test_repo` workspaces.

---

### Task 1: Add Failing Baseline Coverage Test

**Files:**
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [ ] **Step 1: Extend the existing multi-case suite test**

Add assertions after the existing semantic target checks:

```python
    assert result.summary_metrics["baseline_case_count"] == 3
    truncate_case = next(
        case for case in result.case_results if case.case_id == "string-truncate-guard"
    )
    assert truncate_case.baseline_runner_id == "no_patch_baseline"
    assert truncate_case.baseline_stop_reason == "verification_failed"
    assert truncate_case.actual_stop_reason == "verified"
    assert truncate_case.metric_deltas is not None
    assert "verification_count" in truncate_case.metric_deltas

    noop_case = next(case for case in result.case_results if case.case_id == "admin-routes-noop")
    assert noop_case.baseline_runner_id is None
    assert noop_case.baseline_stop_reason is None
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_runs_multiple_cases_with_injected_planner -q
```

Expected: FAIL because `baseline_case_count` is currently `0`.

### Task 2: Implement Semantic No-Patch Baseline Runner

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`

- [ ] **Step 1: Import command request contract**

Add `CommandRunRequest` beside `CommandPolicy`:

```python
from homllm_v4.contracts.command import CommandPolicy, CommandRunRequest
```

- [ ] **Step 2: Assign baseline only to semantic cases**

In `_evaluation_case`, pass:

```python
        baseline_runner_id=(
            "no_patch_baseline" if case.verification_mode != "compile" else None
        ),
```

- [ ] **Step 3: Register baseline runner in the harness**

Create a `run_baseline` closure near `run_case`:

```python
    def run_baseline(case: EvaluationCase) -> CaseExecutionResult:
        return _run_no_patch_baseline(
            case=case,
            source_workspace_root=source_workspace_root,
            workspace_root=workspace_root,
            run_id=resolved_run_id,
            command_service=loop.command_service,
        )
```

Then register both runners:

```python
        runners={
            "real_index_provider_write_verify": run_case,
            "no_patch_baseline": run_baseline,
        },
```

- [ ] **Step 4: Add baseline workspace helper**

Add:

```python
def _copy_baseline_workspace(
    *,
    source_workspace_root: Path,
    workspace_root: Path,
    run_id: str,
    case_id: str,
) -> Path:
    target = workspace_root / run_id / "baselines" / case_id
    if target.exists():
        raise ValueError(f"baseline_workspace_exists: {target}")
    shutil.copytree(source_workspace_root, target)
    return target
```

- [ ] **Step 5: Add no-patch baseline runner**

Add:

```python
def _run_no_patch_baseline(
    *,
    case: EvaluationCase,
    source_workspace_root: Path,
    workspace_root: Path,
    run_id: str,
    command_service: LocalCommandService,
) -> CaseExecutionResult:
    target_file = str(case.input_payload["target_file"])
    baseline_workspace = _copy_baseline_workspace(
        source_workspace_root=source_workspace_root,
        workspace_root=workspace_root,
        run_id=run_id,
        case_id=case.case_id,
    )
    command_result = command_service.run(
        CommandRunRequest(
            task_id=f"{case.case_id}:baseline",
            workspace_root=str(baseline_workspace),
            cwd=".",
            argv=_verification_argv(case, target_file),
            timeout_seconds=15,
        )
    )
    if not command_result.ok or command_result.output is None:
        return CaseExecutionResult(
            stop_reason="verification_failed",
            error_code=command_result.error.code if command_result.error else "command_failed",
            metrics={
                "verification_count": 0,
                "verification_duration_ms": 0,
                "verification_output_chars": 0,
                "verification_output_token_estimate": 0,
            },
        )

    output = command_result.output
    output_chars = len(output.stdout or "") + len(output.stderr or "")
    verified = output.exit_code == 0 and not output.timed_out and not output.denied
    return CaseExecutionResult(
        stop_reason="verified" if verified else "verification_failed",
        error_code=None,
        metrics={
            "verification_count": 1,
            "verification_duration_ms": int(output.duration_ms),
            "verification_output_chars": output_chars,
            "verification_output_token_estimate": output_chars // 4,
        },
    )
```

- [ ] **Step 6: Run targeted test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: all tests in the file pass.

### Task 3: Verify CLI Benchmark and Regression Gates

**Files:**
- No code changes expected.

- [ ] **Step 1: Run real-index benchmark CLI smoke**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_baseline --artifact-root temp\v4_real_index_provider_patch_runs_baseline --run-id real-index-provider-patch-baseline-check --smoke-safe
```

Expected: `6 passed_cases`, `0 failed_cases`, and `baseline_case_count` is `3`.

- [ ] **Step 2: Run v4 unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
```

Expected: all v4 unit tests pass, with live-provider tests skipped unless explicitly enabled.

- [ ] **Step 3: Run full unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
```

Expected: all unit tests pass.

- [ ] **Step 4: Run compile gate**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
```

Expected: exit code `0`.

- [ ] **Step 5: Run v3 import boundary scan**

Run:

```powershell
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected: no output.

### Task 4: Update Audits

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Record new benchmark capability**

Add evidence that semantic real-index write benchmark cases now have a no-patch baseline comparison.

- [ ] **Step 2: Update missing gaps honestly**

Remove the stale statement that no write-task baseline exists. Replace it with the narrower remaining gap: no external/live baseline comparison and no broad write benchmark yet.

- [ ] **Step 3: Record fresh verification counts**

Update the checkpoint evidence with the actual outputs from Task 3.
