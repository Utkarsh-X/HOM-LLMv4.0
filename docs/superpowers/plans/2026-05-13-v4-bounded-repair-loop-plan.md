# v4 Bounded Repair Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the v4 write-execute-verify loop with bounded explicit repair attempts after verification failure.

**Architecture:** The loop still does not generate patches. It accepts a primary patch plus optional precomputed repair patch requests. Runtime owns the repair budget, verification reruns, stop reasons, ledger events, and result artifact.

**Tech Stack:** Python dataclasses, pytest, v4 patch service, v4 command service, artifact manager, ledger writer.

---

## Files

Modify:

- `src/homllm_v4/contracts/write_loop.py`
- `src/homllm_v4/runtime/write_verify_loop.py`
- `src/homllm_v4/ledger/events.py`
- `tests/unit/v4/test_write_verify_loop.py`

## Task 1: Contract Extension

- [ ] Add optional `repair_patch_requests` to `WriteVerifyLoopRequest`.
- [ ] Add `max_patch_attempts` to `WriteVerifyLoopRequest`.
- [ ] Add stop reason `repair_budget_exhausted`.
- [ ] Add `patch_attempt_count` to `WriteVerifyLoopResult`.

## Task 2: Runtime Repair Behavior

- [ ] Apply primary patch as attempt 1.
- [ ] Run all verification commands.
- [ ] If verification fails or times out and repair budget remains, apply the next repair patch.
- [ ] Rerun verification after each repair.
- [ ] Stop with `verified` when all verification commands pass.
- [ ] Stop with `repair_budget_exhausted` when verification still fails and no repair attempt remains.
- [ ] Stop with `patch_failed` if any repair patch fails policy/stale-context checks.

## Task 3: Tests

- [ ] Test a failed primary patch verification followed by successful repair.
- [ ] Test repair budget exhaustion when no repair is provided.
- [ ] Test repair patch stale-context failure stops as `patch_failed`.

## Task 4: Verification

- [ ] Run `pytest tests/unit/v4/test_write_verify_loop.py -q`.
- [ ] Run `pytest tests/unit/v4 -q`.
- [ ] Run boundary test, compileall, and real v3 smoke.

## Explicit Exclusions

- No autonomous repair generation.
- No broad patch scope expansion.
- No dependency installation.
- No shell execution.
