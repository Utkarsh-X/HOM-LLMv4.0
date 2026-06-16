# V4 Write Rollback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit rollback support for failed write verification so v4 can restore workspace files after an applied patch fails verification or times out.

**Architecture:** Rollback is runtime-owned. `WorkspacePatchService.apply()` records enough previous-file state to restore changed files, `WorkspacePatchService.rollback()` performs the restoration, and `WriteVerifyLoop` invokes rollback only when `rollback_on_failure=True`. Rollback does not hide the failure; stop reason remains the original verification failure/timeout/repair exhaustion.

**Tech Stack:** Python dataclasses, existing v4 patch service, existing write-verify loop, pytest.

---

## File Structure

- Modify `src/homllm_v4/contracts/patch.py`
  - Add previous content fields to `FilePatchResult`.
  - Add `PatchRollbackRequest` and `PatchRollbackResult`.
- Modify `src/homllm_v4/services/patch_service.py`
  - Populate previous content fields.
  - Implement `rollback(request)`.
- Modify `src/homllm_v4/contracts/write_loop.py`
  - Add `rollback_on_failure` to `WriteVerifyLoopRequest`.
  - Add `rollback_result` to `WriteVerifyLoopResult`.
- Modify `src/homllm_v4/runtime/write_verify_loop.py`
  - Invoke rollback after failed verification, timeout, verification service failure, or repair exhaustion when enabled.
  - Append a rollback event.
- Modify `src/homllm_v4/ledger/events.py`
  - Add `PATCH_ROLLED_BACK`.
- Modify tests:
  - `tests/unit/v4/test_patch_service.py`
  - `tests/unit/v4/test_write_verify_loop.py`
- Modify architecture audits.

## Task 1: Patch Service Rollback Tests

**Files:**
- Modify: `tests/unit/v4/test_patch_service.py`

- [ ] **Step 1: Add failing rollback test for existing file**

Add a test that:

- writes `demo.py` with `x = 1`
- applies patch to `x = 2`
- calls `service.rollback(PatchRollbackRequest(...))`
- asserts file returns to `x = 1`

- [ ] **Step 2: Add failing rollback test for newly-created file**

Add a test that:

- applies patch creating `new.py`
- rolls back
- asserts `new.py` no longer exists

- [ ] **Step 3: Run test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_patch_service.py::test_patch_service_rolls_back_existing_file -q
```

Expected: FAIL because rollback contracts/service method do not exist.

## Task 2: Patch Service Rollback Implementation

**Files:**
- Modify: `src/homllm_v4/contracts/patch.py`
- Modify: `src/homllm_v4/services/patch_service.py`

- [ ] **Step 1: Add rollback contracts**

Add:

```python
@dataclass(frozen=True)
class FilePatchResult:
    file_path: str
    old_content_hash: str | None
    new_content_hash: str
    diff: str
    old_content: str | None = None
    old_file_existed: bool = True


@dataclass(frozen=True)
class PatchRollbackRequest:
    task_id: str
    workspace_root: str
    file_results: tuple[FilePatchResult, ...]


@dataclass(frozen=True)
class PatchRollbackResult:
    rolled_back: bool
    restored_files: tuple[str, ...]
    deleted_files: tuple[str, ...]
```

- [ ] **Step 2: Populate previous file state in `apply()`**

Set:

- `old_content=old_content if target.exists() else None`
- `old_file_existed=target.exists()`

- [ ] **Step 3: Implement `rollback()`**

Rules:

- path must stay inside workspace
- if `old_file_existed` is true, write `old_content` back
- if `old_file_existed` is false and file exists, delete it
- return structured `CapabilityResult[PatchRollbackResult]`

## Task 3: Write Loop Rollback Tests

**Files:**
- Modify: `tests/unit/v4/test_write_verify_loop.py`

- [ ] **Step 1: Add failing test for rollback after verification failure**

Add a test where:

- patch changes `VALUE = 1` to `VALUE = 2`
- verification command exits nonzero
- request has `rollback_on_failure=True`
- result stop reason remains `verification_failed`
- result has rollback result
- file content is restored to `VALUE = 1`

- [ ] **Step 2: Add failing test proving rollback is opt-in**

Existing `test_write_verify_loop_stops_on_verification_failure` should keep current behavior. Add explicit assertion that file remains changed when rollback is not enabled.

## Task 4: Write Loop Rollback Implementation

**Files:**
- Modify: `src/homllm_v4/contracts/write_loop.py`
- Modify: `src/homllm_v4/runtime/write_verify_loop.py`
- Modify: `src/homllm_v4/ledger/events.py`

- [ ] **Step 1: Add request/result fields**

Add:

```python
rollback_on_failure: bool = False
rollback_result: PatchRollbackResult | None = None
```

- [ ] **Step 2: Invoke rollback on verification failure paths**

When a patch was applied and rollback is enabled, call `patch_service.rollback(...)` before returning the result.

- [ ] **Step 3: Persist rollback result**

Include `rollback_result` in `WriteVerifyLoopResult` artifact.

## Task 5: Verification

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_patch_service.py tests\unit\v4\test_write_verify_loop.py -q
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected:

- targeted rollback tests pass.
- v4/full suites pass.
- compileall passes.
- boundary scan returns no matches.

## Self-Review

- Spec coverage: This implements rollback after applied patches fail verification. It does not implement OS sandboxing, approval UX, or transaction-level rollback across arbitrary shell commands.
- Placeholder scan: No TBD/TODO placeholders are present.
- Type consistency: rollback contract names match service and runtime usage.
