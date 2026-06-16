# V4 Provider-Proposed Fixture Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an end-to-end deterministic fixture suite where a fake provider proposes the edit, v4 plans the patch from evidence, applies it, and verifies it through the existing write-verify loop.

**Architecture:** Keep the existing deterministic patch suite unchanged. Add a sibling provider-proposed suite that uses `ProviderProposedPatchPlanner`, fake fixture retrieval, real direct read, fake provider JSON, and the existing `WriteVerifyLoop`; this proves model-proposal-shaped output can become a verified patch without live provider calls.

**Tech Stack:** Python dataclasses, existing v4 evaluation harness, existing provider planner, existing write-verify loop, pytest, v4 CLI.

---

## File Structure

- Modify `src/homllm_v4/evaluation/fixture_suites.py`
  - Add `run_python_provider_patch_fixture_suite`.
  - Add tiny private fake retrieval/provider helpers scoped to the fixture suite.
- Modify `src/homllm_v4/api.py`
  - Export `run_python_provider_patch_fixture_suite`.
- Modify `src/homllm_v4/cli.py`
  - Add `eval-fixture-provider-patch` command.
- Modify `tests/unit/v4/test_patch_case_evaluation.py`
  - Add unit test for provider-proposed suite.
- Create `tests/unit/v4/test_provider_fixture_cli.py`
  - Add CLI smoke test using `main([...])`.
- Modify architecture audits.

## Task 1: Failing Tests

**Files:**
- Modify: `tests/unit/v4/test_patch_case_evaluation.py`
- Create: `tests/unit/v4/test_provider_fixture_cli.py`

- [ ] **Step 1: Add suite test**

Add a test that calls:

```python
from homllm_v4.evaluation.fixture_suites import run_python_provider_patch_fixture_suite
```

Expected:

- total cases is `2`
- passed cases is `2`
- failed cases is `0`
- `summary_metrics["stop_reason_counts"]["verified"] == 1`
- `summary_metrics["error_code_counts"]["proposal_evidence_scope_denied"] == 1`

- [ ] **Step 2: Run suite test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_patch_case_evaluation.py::test_provider_proposed_fixture_suite_runs_through_evaluation_harness -q
```

Expected: FAIL because `run_python_provider_patch_fixture_suite` does not exist.

- [ ] **Step 3: Add CLI test**

Create `tests/unit/v4/test_provider_fixture_cli.py` with:

```python
from pathlib import Path

from homllm_v4.cli import main


def test_cli_runs_provider_proposed_fixture_suite(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    result = main(
        [
            "eval-fixture-provider-patch",
            "--fixture-root",
            str(repo_root / "fixtures" / "v4" / "python_patch_repo"),
            "--workspace-root",
            str(tmp_path / "work"),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--run-id",
            "provider-cli-test",
        ]
    )

    assert result == 0
    assert (tmp_path / "runs" / "provider-cli-test" / "evaluation" / "summary.json").is_file()
```

## Task 2: Implementation

**Files:**
- Modify: `src/homllm_v4/evaluation/fixture_suites.py`
- Modify: `src/homllm_v4/api.py`
- Modify: `src/homllm_v4/cli.py`

- [ ] **Step 1: Implement `run_python_provider_patch_fixture_suite`**

Use two cases:

- `provider-verified-fix`: provider returns fixed `calculator.py`, expected stop reason `verified`
- `provider-unknown-evidence`: provider references unknown evidence id, expected stop reason `patch_failed`, expected error code `proposal_evidence_scope_denied`

The runner should:

1. Copy the fixture repo for each case.
2. Build a `ProviderProposedPatchPlanner`.
3. Use fake retrieval over the case workspace.
4. Use `DirectReadService`.
5. Use `ProviderBackedEditProposer` with a fake provider returning case JSON.
6. Convert planner output to `WriteVerifyLoopRequest`.
7. Run the existing `WriteVerifyLoop`.
8. Return `CaseExecutionResult` metrics with provider token usage proxies.

- [ ] **Step 2: Add API export**

Import and expose `run_python_provider_patch_fixture_suite` from `src/homllm_v4/api.py`.

- [ ] **Step 3: Add CLI command**

Add command `eval-fixture-provider-patch` with same args as `eval-fixture-patch`.

Expected JSON fields:

- `run_id`
- `total_cases`
- `passed_cases`
- `failed_cases`
- `artifact_root`
- `summary_metrics`

## Task 3: Verification

**Files:**
- Modify docs after tests pass.

- [ ] **Step 1: Run targeted tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_patch_case_evaluation.py::test_provider_proposed_fixture_suite_runs_through_evaluation_harness tests\unit\v4\test_provider_fixture_cli.py -q
```

- [ ] **Step 2: Run full verification**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

- [ ] **Step 3: Run CLI smoke**

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-fixture-provider-patch --fixture-root fixtures\v4\python_patch_repo --workspace-root temp\v4_fixture_provider_patch_work --artifact-root temp\v4_fixture_provider_patch_runs --run-id provider-fixture-check
```

Expected: `failed_cases` is `0`.

## Self-Review

- Spec coverage: This plan covers a deterministic provider-proposed end-to-end fixture path. It does not implement live LLM execution, broad indexed benchmarks, rollback, approval UX, or OS-level sandboxing.
- Placeholder scan: No TBD/TODO placeholders are present.
- Type consistency: suite, API, CLI, and test names are consistent.
