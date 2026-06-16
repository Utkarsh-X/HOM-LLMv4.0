# v4 Case Filter Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `eval-real-index-provider-patch --case-id` fail fast when requested case IDs do not match benchmark cases.

**Architecture:** `run_real_index_provider_patch_suite` already owns case selection. Strengthen `_select_cases(...)` so unknown IDs produce a clear `ValueError` before artifacts, workspaces, provider construction, or live network attempts.

**Tech Stack:** Python, pytest, v4 real-index benchmark suite.

---

## File Structure

- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
  - Validate requested case IDs.
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`
  - Add unknown case-id regression test.
- Modify audits:
  - `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - `docs/v4_architecture/09-active-goal-completion-audit.md`

---

### Task 1: Add Failing Test

**Files:**
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [ ] **Step 1: Add unknown case ID test**

Add:

```python
def test_real_index_provider_patch_suite_rejects_unknown_case_id(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    with pytest.raises(ValueError, match="unknown_case_ids"):
        run_real_index_provider_patch_suite(
            config_path=repo_root / "configs" / "agentic" / "ccg_stage2_canary_v1" / "ccg_stage2_agentic_ro3.yaml",
            source_workspace_root=repo_root / "test_repo",
            workspace_root=tmp_path / "work",
            artifact_root=tmp_path / "runs",
            run_id="unknown-case-suite",
            planner_builder=build_fake_planner,
            case_ids=("does-not-exist",),
        )
```

- [ ] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_rejects_unknown_case_id -q
```

Expected: FAIL because current filtering silently returns zero cases.

---

### Task 2: Implement Validation

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`

- [ ] **Step 1: Update `_select_cases`**

Replace current function with:

```python
def _select_cases(case_ids: tuple[str, ...] | None) -> tuple[RealIndexProviderPatchCase, ...]:
    if case_ids is None:
        return REAL_INDEX_PROVIDER_PATCH_CASES

    available = {case.case_id for case in REAL_INDEX_PROVIDER_PATCH_CASES}
    requested = set(case_ids)
    unknown = tuple(sorted(requested - available))
    if unknown:
        raise ValueError(f"unknown_case_ids: {', '.join(unknown)}")

    selected = tuple(case for case in REAL_INDEX_PROVIDER_PATCH_CASES if case.case_id in requested)
    if not selected:
        raise ValueError("no_case_ids_selected")
    return selected
```

- [ ] **Step 2: Run targeted tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: pass.

---

### Task 3: Verification and Audit

- [ ] **Step 1: Run full verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

- [ ] **Step 2: Update audits**

Record that live/case-limited benchmark execution has case-id validation so accidental empty runs cannot masquerade as successful coverage.

---

## Self-Review

Spec coverage:

- Prevents silent zero-case or typo-case benchmark execution.
- Improves live-mode safety because case filters are often used to control cost.

Placeholder scan:

- No placeholder tasks remain.

Type consistency:

- Uses existing `case_ids` argument and case dataclass.

