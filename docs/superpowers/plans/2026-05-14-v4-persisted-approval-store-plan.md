# V4 Persisted Approval Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist approval requests and decisions to an append-only JSONL file and replay them into `ApprovalRegistry`.

**Architecture:** Approval UI is still out of scope. This adds durable audit/replay support only: a store appends `{request, decision}` records, flushes immediately, and can rebuild an in-memory registry from disk. Command execution remains dependent on `ApprovalRegistry`, not direct file reads.

**Tech Stack:** Python dataclasses, JSONL, existing v4 approval contracts, pytest.

---

## File Structure

- Create `src/homllm_v4/services/approval_store.py`
  - Defines `ApprovalStore.append()` and `ApprovalStore.load_registry()`.
- Modify `tests/unit/v4/test_approval_service.py`
  - Add persisted approval store tests.
- Modify architecture audits.

## Task 1: Failing Store Tests

**Files:**
- Modify: `tests/unit/v4/test_approval_service.py`

- [ ] **Step 1: Add failing persistence test**

Add test:

- create `ApprovalStore(tmp_path / "approvals.jsonl")`
- append request+decision
- assert JSONL file exists with one line
- load registry
- assert registry approves matching command

- [ ] **Step 2: Add failing invalid-record test**

Add test:

- write malformed/non-object line to store path
- `load_registry()` raises `ValueError("approval_store_corrupt")`

- [ ] **Step 3: Run first test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_approval_service.py::test_approval_store_persists_and_replays_registry -q
```

Expected: FAIL because `approval_store` does not exist.

## Task 2: Store Implementation

**Files:**
- Create: `src/homllm_v4/services/approval_store.py`

- [ ] **Step 1: Implement append**

Rules:

- write exactly one JSON line per approval record
- use `to_jsonable`
- create parent directory
- flush after write

- [ ] **Step 2: Implement replay**

Rules:

- if file does not exist, return empty `ApprovalRegistry`
- each line must be JSON object with `request` and `decision`
- reconstruct `ApprovalRequest` and `ApprovalDecision`
- record each pair into registry
- raise `ValueError("approval_store_corrupt")` on malformed records

## Task 3: Verification

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

- Spec coverage: This persists approval decisions for audit/replay. It does not implement UI prompts, secrets, user identity, or multi-process locking.
- Placeholder scan: No TBD/TODO placeholders are present.
- Type consistency: store methods use existing `ApprovalRequest`, `ApprovalDecision`, and `ApprovalRegistry`.
