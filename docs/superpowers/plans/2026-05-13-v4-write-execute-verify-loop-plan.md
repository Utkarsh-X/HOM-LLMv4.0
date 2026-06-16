# v4 Write Execute Verify Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compose the existing v4 patch and command primitives into a bounded write-execute-verify loop with typed stop reasons, attempt limits, and inspectable artifacts.

**Architecture:** The loop does not plan patches with an LLM. It accepts an explicit patch request and verification command sequence, applies the patch through `WorkspacePatchService`, executes verification through `LocalCommandService`, and stops deterministically. Runtime owns stop reasons and artifact persistence.

**Tech Stack:** Python dataclasses, pytest, v4 patch service, v4 command service, artifact manager, ledger writer.

---

## Files

Create:

- `src/homllm_v4/contracts/write_loop.py`
- `src/homllm_v4/runtime/write_verify_loop.py`
- `tests/unit/v4/test_write_verify_loop.py`

Modify:

- `src/homllm_v4/ledger/events.py`

## Task 1: Contracts

- [ ] Add request/result contracts for a bounded write-verify run.
- [ ] Required stop reasons: `verified`, `patch_failed`, `verification_failed`, `verification_timeout`, `budget_exhausted`.
- [ ] Result must include patch result, verification results, response text, and optional error.

## Task 2: Loop Runtime

- [ ] Apply patch once through `WorkspacePatchService`.
- [ ] If patch fails, stop with `patch_failed`.
- [ ] Run verification commands in order through `LocalCommandService`.
- [ ] Stop at first failed or timed-out verification.
- [ ] Stop with `verified` only if all verification commands exit `0`.

## Task 3: Artifacts And Ledger

- [ ] Emit ledger events for patch attempt, patch result, verification command result, and run completion.
- [ ] Persist `response/write_verify_loop_result.json`.

## Task 4: Verification

- [ ] Run `pytest tests/unit/v4/test_write_verify_loop.py -q`.
- [ ] Run `pytest tests/unit/v4 -q`.
- [ ] Run boundary tests and compileall.

## Explicit Exclusions

- No autonomous patch generation.
- No repair loop.
- No dependency installation.
- No command shell.
- No elevated/full-access execution.
