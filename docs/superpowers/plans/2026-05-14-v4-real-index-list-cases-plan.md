# v4 Real-Index List Cases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `eval-real-index-provider-patch --list-cases` so users can inspect benchmark case IDs and targets before running fake or live provider benchmarks.

**Architecture:** The benchmark suite owns case metadata. The CLI list mode prints JSON and returns before workspace copying, retrieval, provider construction, or verification. This is a low-risk safety/UX feature for live runs.

**Tech Stack:** Python, pytest, v4 CLI and real-index benchmark suite.

---

## File Structure

- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
  - Add `real_index_provider_patch_case_metadata()`.
- Modify: `src/homllm_v4/api.py`
  - Export metadata helper.
- Modify: `src/homllm_v4/cli.py`
  - Add `--list-cases` to `eval-real-index-provider-patch`.
- Modify: `tests/unit/v4/test_provider_fixture_cli.py`
  - Add CLI test for list mode.
- Modify audits:
  - `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - `docs/v4_architecture/09-active-goal-completion-audit.md`

---

### Task 1: Add Failing CLI Test

**Files:**
- Modify: `tests/unit/v4/test_provider_fixture_cli.py`

- [ ] **Step 1: Add list-cases test**

Add:

```python
def test_cli_lists_real_index_provider_patch_cases(capsys) -> None:
    result = main(["eval-real-index-provider-patch", "--list-cases"])
    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["command"] == "eval-real-index-provider-patch"
    assert payload["case_count"] >= 6
    assert any(case["case_id"] == "admin-routes-noop" for case in payload["cases"])
    assert any(case["case_id"] == "validate-email-local-dot-guard" for case in payload["cases"])
```

- [ ] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_lists_real_index_provider_patch_cases -q
```

Expected: FAIL because `--list-cases` does not exist and required args are still required.

---

### Task 2: Implement Metadata Helper and CLI Mode

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
- Modify: `src/homllm_v4/api.py`
- Modify: `src/homllm_v4/cli.py`

- [ ] **Step 1: Add metadata helper**

Implement:

```python
def real_index_provider_patch_case_metadata() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "case_id": case.case_id,
            "target_file": case.target_file,
            "query": case.query,
            "provider_mode": case.provider_mode,
            "verification_mode": case.verification_mode,
        }
        for case in REAL_INDEX_PROVIDER_PATCH_CASES
    )
```

- [ ] **Step 2: Export helper from API**

Import it in `src/homllm_v4/api.py`.

- [ ] **Step 3: Make real-index required args conditional**

For the `eval-real-index-provider-patch` parser, make these not parser-required:

```text
--config
--source-workspace-root
--workspace-root
--artifact-root
```

Add:

```text
--list-cases
```

In command branch:

```python
if args.list_cases:
    cases = real_index_provider_patch_case_metadata()
    print(json.dumps({"command": args.command, "case_count": len(cases), "cases": cases}, sort_keys=True))
    return 0
```

For non-list mode, validate missing required args using `parser.error(...)` or structured error. Prefer structured JSON:

```python
missing = tuple(name for name in (...) if getattr(args, attr) is None)
if missing:
    print(json.dumps({"command": args.command, "error_code": "missing_required_args", "missing": missing}, sort_keys=True))
    return 2
```

- [ ] **Step 4: Run targeted CLI tests**

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

Record that case metadata can be listed without running the benchmark, improving live-run safety and scriptability.

---

## Self-Review

Spec coverage:

- Adds explicit case discoverability before live runs.
- Avoids provider/retrieval execution in list mode.
- Keeps benchmark metadata in the suite module.

Placeholder scan:

- No placeholder tasks remain.

Type consistency:

- Uses existing case dataclass fields and CLI command name.

