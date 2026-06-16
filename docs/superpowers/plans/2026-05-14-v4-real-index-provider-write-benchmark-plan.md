# v4 Real-Index Provider Write Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable multi-case real-index provider-proposed write benchmark path that copies `test_repo`, uses v3 indexed retrieval through adapters, keeps the provider fake by default, applies patches through v4, and emits evaluation summaries.

**Architecture:** A new evaluation module owns the benchmark cases and runtime orchestration. Default unit tests inject a fake planner to avoid real indexes; opt-in CLI runs use `build_v3_provider_proposed_patch_planner` and local `indexes/` through the adapter boundary.

**Tech Stack:** Python, pytest, v4 evaluation harness, v4 write/verify loop, existing v3 provider patch planner adapter, PowerShell CLI smoke.

---

## File Structure

- Create: `src/homllm_v4/evaluation/real_index_provider_suites.py`
  - Defines real-index provider write cases.
  - Copies `test_repo` per case.
  - Uses fake provider proposals by default.
  - Runs planning, patch application, and verification through v4 contracts.
- Modify: `src/homllm_v4/api.py`
  - Export `run_real_index_provider_patch_suite`.
- Modify: `src/homllm_v4/cli.py`
  - Add `eval-real-index-provider-patch` command.
- Create: `tests/unit/v4/test_real_index_provider_patch_suite.py`
  - Unit-tests the suite with injected fake planner builder.
- Modify: `tests/unit/v4/test_provider_fixture_cli.py`
  - Adds CLI parser/entrypoint test with injected API seam if needed.
- Modify audits:
  - `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - `docs/v4_architecture/09-active-goal-completion-audit.md`

---

### Task 1: Add Failing Suite API Test

**Files:**
- Create: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [ ] **Step 1: Write the failing test**

Create a test importing:

```python
from homllm_v4.evaluation.real_index_provider_suites import run_real_index_provider_patch_suite
```

The test should:

```python
def test_real_index_provider_patch_suite_runs_multiple_cases_with_injected_planner(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    result = run_real_index_provider_patch_suite(
        config_path=repo_root / "configs" / "agentic" / "ccg_stage2_canary_v1" / "ccg_stage2_agentic_ro3.yaml",
        source_workspace_root=repo_root / "test_repo",
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="real-index-provider-suite",
        planner_builder=build_fake_planner,
    )

    assert result.total_cases >= 3
    assert result.passed_cases == result.total_cases
    assert result.failed_cases == 0
    assert result.summary_metrics["stop_reason_counts"]["verified"] >= 3
    assert (tmp_path / "runs" / "real-index-provider-suite" / "evaluation" / "summary.json").is_file()
```

Add a local `build_fake_planner` that returns `ProviderProposedPatchPlanner` with:

- fake retrieval service returning one candidate for `request.target_files[0]`
- `DirectReadService(workspace_root=workspace_root)`
- `ProviderBackedEditProposer(provider=edit_provider)`

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_runs_multiple_cases_with_injected_planner -q
```

Expected: FAIL because `homllm_v4.evaluation.real_index_provider_suites` does not exist.

---

### Task 2: Implement Benchmark Suite

**Files:**
- Create: `src/homllm_v4/evaluation/real_index_provider_suites.py`

- [ ] **Step 1: Implement fixed benchmark cases**

Define three verified no-op cases:

```python
("admin-routes-noop", "api/routes.py", "admin_search_endpoint in api routes")
("cache-manager-noop", "cache/cache_manager.py", "multi level cache miss fallback")
("metrics-noop", "monitoring/metrics.py", "metrics collector counters gauges histograms")
```

Each case:

- copies `source_workspace_root` to `workspace_root / run_id / "cases" / case_id`
- reads `target_file`
- creates a prompt-aware fake provider returning the exact current content
- asks the planner for a patch
- runs `WriteVerifyLoop`
- verifies with `(sys.executable, "-m", "compileall", "-q", target_file)`

- [ ] **Step 2: Implement result metrics**

Each `CaseExecutionResult.metrics` should include:

```python
{
    "patch_attempt_count": result.patch_attempt_count,
    "verification_count": len(result.verification_results),
    "verification_duration_ms": sum(...),
    "verification_output_chars": output_chars,
    "verification_output_token_estimate": output_chars // 4,
    "provider_tokens_in": provider.tokens_in,
    "provider_tokens_out": provider.tokens_out,
}
```

- [ ] **Step 3: Preserve non-overwrite behavior**

If a case workspace already exists, raise:

```python
ValueError(f"case_workspace_exists: {target}")
```

This matches the existing fixture suite behavior.

- [ ] **Step 4: Run targeted test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: pass.

---

### Task 3: Add API and CLI Entrypoint

**Files:**
- Modify: `src/homllm_v4/api.py`
- Modify: `src/homllm_v4/cli.py`
- Modify: `tests/unit/v4/test_provider_fixture_cli.py`

- [ ] **Step 1: Export API function**

Update `api.py` import list:

```python
from homllm_v4.evaluation.real_index_provider_suites import run_real_index_provider_patch_suite
```

- [ ] **Step 2: Add CLI parser**

Add subcommand:

```text
eval-real-index-provider-patch
```

Arguments:

```text
--config
--source-workspace-root
--workspace-root
--artifact-root
--run-id
--smoke-safe
```

- [ ] **Step 3: Add CLI execution branch**

Call `run_real_index_provider_patch_suite(...)` and print the same JSON shape as other eval commands.

- [ ] **Step 4: Add CLI unit test**

Add a test that monkeypatches `homllm_v4.cli.run_real_index_provider_patch_suite` with a fake function returning `EvaluationRunResult`.

Assert:

```python
assert result == 0
assert captured_kwargs["config_path"].name == "ccg_stage2_agentic_ro3.yaml"
assert captured_kwargs["source_workspace_root"].name == "test_repo"
```

- [ ] **Step 5: Run CLI tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py -q
```

Expected: pass.

---

### Task 4: Run Real-Index Opt-In CLI Smoke

**Files:**
- No production file changes expected.

- [ ] **Step 1: Run fresh real-index CLI benchmark**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work --artifact-root temp\v4_real_index_provider_patch_runs --run-id real-index-provider-patch-check --smoke-safe
```

Expected:

- `failed_cases` is `0`
- `passed_cases` is at least `3`

If the exact workspace/run id already exists, rerun with fresh names.

---

### Task 5: Verification Gate and Audits

**Files:**
- Modify:
  - `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Run verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected:

- v4 and full unit suites pass.
- compile exits `0`.
- boundary scan returns no output.

- [ ] **Step 2: Update audits**

Record:

- multi-case real-index provider write benchmark exists
- default tests use injected fake planner
- real CLI smoke passed with fake provider and real v3 retrieval
- still no live provider synthesis benchmark
- still no external baseline write comparison

---

## Self-Review

Spec coverage:

- The plan creates a reusable multi-case benchmark path, not just another one-off smoke.
- It keeps provider behavior fake-provider-first by default.
- Real v3 retrieval remains behind adapter factory and CLI/API boundaries.
- It does not add live provider calls or autonomous target-file selection.

Placeholder scan:

- No placeholder task remains. Commands and file paths are concrete.

Type consistency:

- The plan uses existing `EvaluationRunResult`, `EvaluationCase`, `CaseExecutionResult`, `ProviderProposedPatchPlanner`, and `WriteVerifyLoop` APIs.

