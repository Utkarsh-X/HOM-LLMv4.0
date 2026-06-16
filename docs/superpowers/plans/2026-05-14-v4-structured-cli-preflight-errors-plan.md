# v4 Structured CLI Preflight Errors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `eval-real-index-provider-patch` return structured JSON for benchmark preflight failures instead of surfacing Python exceptions.

**Architecture:** Keep validation in the benchmark suite. The CLI catches `ValueError` from `run_real_index_provider_patch_suite(...)`, prints a small JSON error envelope, and returns nonzero. This is only for the real-index benchmark command for now because that is where live/case-filter preflights exist.

**Tech Stack:** Python, pytest, v4 CLI.

---

## File Structure

- Modify: `src/homllm_v4/cli.py`
  - Catch `ValueError` around the real-index provider benchmark call.
  - Print structured JSON with `error_code`, `message`, and `command`.
- Modify: `tests/unit/v4/test_provider_fixture_cli.py`
  - Add tests for missing live API key and unknown case id CLI errors.
- Modify audits:
  - `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - `docs/v4_architecture/09-active-goal-completion-audit.md`

---

### Task 1: Add Failing CLI Tests

**Files:**
- Modify: `tests/unit/v4/test_provider_fixture_cli.py`

- [ ] **Step 1: Import json**

Add:

```python
import json
```

- [ ] **Step 2: Add missing-key CLI test**

Add:

```python
def test_cli_reports_real_index_live_mode_missing_key_as_json(capsys, tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = main([... "--edit-provider-mode", "live", "--case-id", "admin-routes-noop"])

    payload = json.loads(capsys.readouterr().out)
    assert result == 1
    assert payload["command"] == "eval-real-index-provider-patch"
    assert payload["error_code"] == "live_provider_api_key_required"
```

- [ ] **Step 3: Add unknown-case CLI test**

Add:

```python
def test_cli_reports_real_index_unknown_case_id_as_json(capsys, tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = main([... "--case-id", "does-not-exist"])

    payload = json.loads(capsys.readouterr().out)
    assert result == 1
    assert payload["command"] == "eval-real-index-provider-patch"
    assert payload["error_code"] == "unknown_case_ids"
```

- [ ] **Step 4: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_reports_real_index_live_mode_missing_key_as_json tests\unit\v4\test_provider_fixture_cli.py::test_cli_reports_real_index_unknown_case_id_as_json -q
```

Expected: FAIL because `ValueError` escapes instead of returning JSON.

---

### Task 2: Implement CLI Error Envelope

**Files:**
- Modify: `src/homllm_v4/cli.py`

- [ ] **Step 1: Add helper**

Add:

```python
def _error_code(exc: ValueError) -> str:
    return str(exc).split(":", 1)[0]
```

- [ ] **Step 2: Catch real-index preflight errors**

Wrap `run_real_index_provider_patch_suite(...)` with:

```python
try:
    result = run_real_index_provider_patch_suite(...)
except ValueError as exc:
    print(json.dumps({
        "command": args.command,
        "error_code": _error_code(exc),
        "message": str(exc),
    }, sort_keys=True))
    return 1
```

- [ ] **Step 3: Run targeted tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py -q
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

Record structured CLI preflight errors for live missing-key and unknown case ids.

---

## Self-Review

Spec coverage:

- Makes live benchmark setup safer and more scriptable.
- Does not change fake-mode success behavior.

Placeholder scan:

- No placeholder tasks remain.

Type consistency:

- Uses existing CLI `main(...)` and suite `ValueError` messages.

