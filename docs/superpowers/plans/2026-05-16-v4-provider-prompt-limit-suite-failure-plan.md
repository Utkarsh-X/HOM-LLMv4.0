# V4 Provider Prompt Limit Suite Failure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the real-index provider patch suite fails safely and observably when the provider prompt exceeds the configured prompt-character cap.

**Architecture:** The prompt cap already exists at `ProviderBackedEditProposer` and is exposed through the real-index provider patch suite/CLI. This slice adds an end-to-end suite-level regression test using the fake planner path, then updates the test planner helper so injected planners receive the same `max_prompt_chars` policy as production planners.

**Tech Stack:** Python dataclasses, pytest, HOM-LLM v4 evaluation harness, fake provider-backed planner.

---

### Task 1: Suite-Level Prompt Cap Failure Guard

**Files:**
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`
- Read: `src/homllm_v4/evaluation/real_index_provider_suites.py`

- [x] **Step 1: Write the failing test**

Add this test to `tests/unit/v4/test_real_index_provider_patch_suite.py`:

```python
def test_real_index_provider_patch_suite_prompt_limit_fails_before_provider_call(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = run_real_index_provider_patch_suite(
        config_path=repo_root
        / "configs"
        / "agentic"
        / "ccg_stage2_canary_v1"
        / "ccg_stage2_agentic_ro3.yaml",
        source_workspace_root=repo_root / "test_repo",
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="prompt-limit-suite",
        planner_builder=build_fake_planner,
        case_ids=("admin-routes-noop",),
        max_prompt_chars=10,
    )

    assert result.total_cases == 1
    assert result.passed_cases == 0
    assert result.failed_cases == 1
    case = result.case_results[0]
    assert case.case_id == "admin-routes-noop"
    assert case.actual_stop_reason == "patch_failed"
    assert case.error_code == "provider_prompt_budget_exceeded"
    assert result.summary_metrics["error_code_counts"] == {
        "provider_prompt_budget_exceeded": 1
    }
    assert (
        tmp_path
        / "runs"
        / "prompt-limit-suite"
        / "provider"
        / "admin-routes-noop"
        / "prompt.txt"
    ).is_file()
```

- [x] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_prompt_limit_fails_before_provider_call -q
```

Expected: FAIL because the injected `build_fake_planner` helper does not yet accept and pass `max_prompt_chars`, so the cap is not applied on this path.

- [x] **Step 3: Pass prompt cap through the injected fake planner**

Change the helper signature in `tests/unit/v4/test_real_index_provider_patch_suite.py`:

```python
def build_fake_planner(
    *,
    config_path: Path,
    workspace_root: Path,
    edit_provider,
    smoke_safe: bool = True,
    artifact_manager=None,
    max_prompt_chars: int | None = None,
) -> ProviderProposedPatchPlanner:
```

Change the proposer construction:

```python
edit_proposer=ProviderBackedEditProposer(
    provider=edit_provider,
    artifact_manager=artifact_manager,
    max_prompt_chars=max_prompt_chars,
),
```

- [x] **Step 4: Run the focused test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_prompt_limit_fails_before_provider_call -q
```

Expected: PASS.

- [x] **Step 5: Run suite-level regression tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: PASS.

- [x] **Step 6: Verify the real CLI failure mode**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_prompt_limit_failure --artifact-root temp\v4_real_index_provider_patch_runs_prompt_limit_failure --run-id real-index-provider-patch-prompt-limit-failure-check --case-id admin-routes-noop --max-prompt-chars 10 --smoke-safe
```

Expected: exit code 1 with JSON showing `failed_cases: 1`, `passed_cases: 0`, and `error_code_counts.provider_prompt_budget_exceeded: 1`.

- [x] **Step 7: Update audit docs**

Add the new guard evidence to:

```text
docs/v4_architecture/08-milestone-1-4-implementation-audit.md
docs/v4_architecture/09-active-goal-completion-audit.md
```

Record that the suite and CLI can now prove prompt cap failures are structured and provider-safe.

- [x] **Step 8: Run final verification gates**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected: all pytest/compile commands pass, and the boundary scan prints no matches.
