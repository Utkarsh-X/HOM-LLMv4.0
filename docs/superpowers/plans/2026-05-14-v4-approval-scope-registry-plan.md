# V4 Approval Scope Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small approval scope registry so approval-gated command execution can be allowed by explicit once/task/session decisions without collapsing approval policy into sandbox policy.

**Architecture:** Approval decisions are runtime data. `ApprovalRegistry` records approved or denied decisions and resolves scope. `LocalCommandService` remains non-interactive: if a command is approval-gated and no matching approval exists, it returns `requires_approval`; if a matching approval exists, it executes through the same structured argv/local sandbox path.

**Tech Stack:** Python dataclasses, existing v4 command service, pytest.

---

## File Structure

- Create `src/homllm_v4/contracts/approval.py`
  - Defines `ApprovalRequest`, `ApprovalDecision`, and approval scope literals.
- Create `src/homllm_v4/services/approval_service.py`
  - Defines `ApprovalRegistry` with `record()` and `is_approved()`.
- Modify `src/homllm_v4/services/command_service.py`
  - Accept optional `approval_registry` and `session_id`.
  - Allow execution of approval-gated executable only when registry approves the capability.
- Modify `tests/unit/v4/test_approval_service.py`
  - Tests once/task/session approval behavior.
- Modify `tests/unit/v4/test_command_service.py`
  - Tests approval-gated command executes after approval.
- Modify architecture audits.

## Task 1: Approval Registry Tests

**Files:**
- Create: `tests/unit/v4/test_approval_service.py`

- [ ] **Step 1: Add failing tests**

Tests:

- once approval is consumed after one check
- task approval works only for matching task
- session approval works across tasks in same session
- denied decision never approves

- [ ] **Step 2: Run first test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_approval_service.py::test_once_approval_is_consumed_after_first_use -q
```

Expected: FAIL because approval contracts/service do not exist.

## Task 2: Registry Implementation

**Files:**
- Create: `src/homllm_v4/contracts/approval.py`
- Create: `src/homllm_v4/services/approval_service.py`

- [ ] **Step 1: Add contracts**

```python
ApprovalScope = Literal["once", "task", "session"]

@dataclass(frozen=True)
class ApprovalRequest:
    request_id: str
    task_id: str
    session_id: str
    requested_capability: str
    subject: str
    reason: str

@dataclass(frozen=True)
class ApprovalDecision:
    request_id: str
    approved: bool
    scope: ApprovalScope
    approver: str
```

- [ ] **Step 2: Add registry**

`ApprovalRegistry.record(request, decision)` stores approvals/denials.

`ApprovalRegistry.is_approved(task_id, session_id, requested_capability, subject)` returns true when a matching approved decision exists.

Scope rules:

- `once`: first match returns true and consumes the grant
- `task`: matches same task id
- `session`: matches same session id
- denied decisions do not approve

## Task 3: Command Service Integration

**Files:**
- Modify: `src/homllm_v4/services/command_service.py`
- Modify: `tests/unit/v4/test_command_service.py`

- [ ] **Step 1: Add failing command test**

Test:

- command executable is approval-gated
- registry has approved session decision
- command executes and returns ok

- [ ] **Step 2: Implement command integration**

`LocalCommandService.__init__` accepts:

```python
approval_registry: ApprovalRegistry | None = None
session_id: str = "default"
```

When executable is in `approval_required_executables`:

- if registry approves `command_execution` for that executable, continue to execution
- else return `requires_approval`

## Task 4: Verification

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_approval_service.py tests\unit\v4\test_command_service.py -q
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected:

- approval and command tests pass.
- v4/full suites pass.
- compileall passes.
- boundary scan returns no matches.

## Self-Review

- Spec coverage: This implements approval scope resolution but not product UI, persisted disk storage, or human prompt flows.
- Placeholder scan: No TBD/TODO placeholders are present.
- Type consistency: approval capability names use `command_execution`, matching command-service details.
