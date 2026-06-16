# v4 Evaluation Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal deterministic evaluation harness for v4 runtime paths so read-only and write-verify behavior can be measured before larger benchmarks.

**Architecture:** The harness is runner-agnostic. Each case names a `runner_id`, expected stop reason, and payload. Runtime-specific adapters can be added later. This milestone records pass/fail, stop reason, metrics, errors, and a persisted JSON summary.

**Tech Stack:** Python dataclasses, pytest, artifact manager, v4 serialization.

---

## Files

Create:

- `src/homllm_v4/contracts/evaluation.py`
- `src/homllm_v4/evaluation/__init__.py`
- `src/homllm_v4/evaluation/harness.py`
- `tests/unit/v4/test_evaluation_harness.py`

## Task 1: Contracts

- [ ] Add `EvaluationCase`, `CaseExecutionResult`, `EvaluationCaseResult`, and `EvaluationRunResult`.
- [ ] Cases include `case_id`, `runner_id`, `task_type`, `input_payload`, `expected_stop_reason`.

## Task 2: Harness

- [ ] Implement `V4EvaluationHarness`.
- [ ] It accepts runner callables keyed by `runner_id`.
- [ ] Unknown runner produces a failed case result, not an exception.
- [ ] A case passes when actual stop reason equals expected stop reason and execution did not report an error.

## Task 3: Persistence

- [ ] Persist `evaluation/summary.json` through `ArtifactManager`.
- [ ] Include totals: case count, passed, failed.

## Task 4: Verification

- [ ] Run `pytest tests/unit/v4/test_evaluation_harness.py -q`.
- [ ] Run `pytest tests/unit/v4 -q`.
- [ ] Run boundary tests, compileall, and real v3 smoke.

## Explicit Exclusions

- No LLM judge.
- No baseline comparison.
- No SWE-bench/Terminal-bench integration.
- No expensive real runtime execution by default.
