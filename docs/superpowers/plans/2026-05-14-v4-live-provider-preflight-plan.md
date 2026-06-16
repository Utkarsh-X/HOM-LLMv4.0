# v4 Live Provider Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent accidental live-provider benchmark execution without an explicit API key.

**Architecture:** The real-index benchmark already has fake default mode and opt-in live mode. Add a preflight validation that rejects `edit_provider_mode="live"` when no API key is supplied, before copying case workspaces or invoking provider construction.

**Tech Stack:** Python, pytest, v4 real-index benchmark suite.

---

## File Structure

- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
  - Add live-mode preflight validation.
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`
  - Add test for missing live API key.
- Modify audits:
  - `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - `docs/v4_architecture/09-active-goal-completion-audit.md`

---

### Task 1: Add Failing Preflight Test

**Files:**
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [ ] **Step 1: Add pytest import if needed**

```python
import pytest
```

- [ ] **Step 2: Add missing-key test**

Add:

```python
def test_real_index_provider_patch_suite_rejects_live_mode_without_api_key(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    with pytest.raises(ValueError, match="live_provider_api_key_required"):
        run_real_index_provider_patch_suite(
            config_path=repo_root / "configs" / "agentic" / "ccg_stage2_canary_v1" / "ccg_stage2_agentic_ro3.yaml",
            source_workspace_root=repo_root / "test_repo",
            workspace_root=tmp_path / "work",
            artifact_root=tmp_path / "runs",
            run_id="missing-live-key-suite",
            planner_builder=build_fake_planner,
            edit_provider_mode="live",
            live_provider_name="gemini",
            live_model="gemini-live-test",
            live_api_key=None,
            case_ids=("admin-routes-noop",),
        )
```

- [ ] **Step 3: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_rejects_live_mode_without_api_key -q
```

Expected: FAIL because live mode currently accepts `None`.

---

### Task 2: Implement Preflight

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`

- [ ] **Step 1: Add validation near start of suite**

Before `ArtifactManager.create_run(...)`, add:

```python
_validate_provider_mode(
    edit_provider_mode=edit_provider_mode,
    live_api_key=live_api_key,
)
```

Implement:

```python
def _validate_provider_mode(*, edit_provider_mode: str, live_api_key: str | None) -> None:
    if edit_provider_mode == "fake":
        return
    if edit_provider_mode == "live":
        if not live_api_key:
            raise ValueError("live_provider_api_key_required")
        return
    raise ValueError(f"unsupported edit_provider_mode: {edit_provider_mode}")
```

This makes unsupported-mode failure happen before side effects too.

- [ ] **Step 2: Simplify `_build_edit_provider` unsupported branch**

Keep the existing unsupported branch or leave it as defense-in-depth.

- [ ] **Step 3: Run targeted test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: pass.

---

### Task 3: Verification and Audit

- [ ] **Step 1: Run verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

- [ ] **Step 2: Update audits**

Record that live mode has an explicit API key preflight, reducing accidental network/cost attempts.

---

## Self-Review

Spec coverage:

- Adds a concrete safety gate for the live path.
- Does not change fake mode or require network access.

Placeholder scan:

- No placeholder tasks remain.

Type consistency:

- Uses existing `run_real_index_provider_patch_suite` arguments.

