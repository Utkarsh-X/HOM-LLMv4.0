# V4 Command Approval Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a structured command approval result so high-risk commands can be blocked as `requires_approval` instead of being mixed with ordinary command denials.

**Architecture:** Approval remains separate from sandboxing. `LocalCommandService` still never escalates or prompts directly; it only returns a structured `CapabilityError(code="requires_approval")` when policy marks an executable as approval-gated. A future approval UI can consume that contract and retry with a different policy.

**Tech Stack:** Python dataclasses, existing v4 command contracts/service, pytest.

---

## File Structure

- Modify `src/homllm_v4/contracts/command.py`
  - Add `approval_required_executables` to `CommandPolicy`.
- Modify `src/homllm_v4/services/command_service.py`
  - Return `requires_approval` before execution when executable is approval-gated.
- Modify `tests/unit/v4/test_command_service.py`
  - Add approval-required test.
- Modify architecture audits.

## Task 1: Failing Test

**Files:**
- Modify: `tests/unit/v4/test_command_service.py`

- [ ] **Step 1: Add approval-required test**

Add a test where:

- `allowed_executables=()`
- `approval_required_executables=(Path(sys.executable).name,)`
- command uses `sys.executable`
- result is not ok
- error code is `requires_approval`
- details include `approval_scope="command_execution"`

- [ ] **Step 2: Run test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_command_service.py::test_command_service_returns_requires_approval_for_approval_gated_executable -q
```

Expected: FAIL because `approval_required_executables` is not supported.

## Task 2: Implementation

**Files:**
- Modify: `src/homllm_v4/contracts/command.py`
- Modify: `src/homllm_v4/services/command_service.py`

- [ ] **Step 1: Add policy field**

```python
approval_required_executables: tuple[str, ...] = ()
```

- [ ] **Step 2: Add approval check before allowlist denial**

If executable is in `approval_required_executables`, return failed `CapabilityResult` with:

```python
code="requires_approval"
details={
    "argv": request.argv,
    "cwd": request.cwd,
    "approval_scope": "command_execution",
    "executable": executable,
}
```

Do not execute the command.

## Task 3: Verification

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_command_service.py -q
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected:

- command tests pass.
- v4/full suites pass.
- compileall passes.
- boundary scan returns no matches.

## Self-Review

- Spec coverage: This implements the first approval contract for commands. It does not implement an interactive approval UI, persisted approval scopes, or escalation retries.
- Placeholder scan: No TBD/TODO placeholders are present.
- Type consistency: `requires_approval` matches the architecture document stop/error taxonomy.
