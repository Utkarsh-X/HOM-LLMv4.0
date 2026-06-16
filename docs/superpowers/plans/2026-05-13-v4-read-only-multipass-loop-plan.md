# v4 Read-Only Multipass Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first HOM-LLM v4 read-only multipass loop with typed state, deterministic sufficiency, evidence-overlap repetition guarding, stop reasons, and grounded response metadata.

**Architecture:** Runtime owns the loop. Services remain capability boundaries. No LLM planning, command execution, patching, write tools, or product memory are introduced in this milestone.

**Tech Stack:** Python dataclasses, pytest, v4 `CapabilityResult`, existing service registry, existing ledger writer.

---

## Files

Create:

- `src/homllm_v4/contracts/loop.py`
- `src/homllm_v4/runtime/__init__.py`
- `src/homllm_v4/runtime/repetition_guard.py`
- `src/homllm_v4/runtime/sufficiency.py`
- `src/homllm_v4/runtime/read_only_loop.py`
- `tests/unit/v4/test_read_only_loop.py`

Modify:

- `src/homllm_v4/ledger/events.py`

## Task 1: Loop Contracts

- [ ] Add loop contracts for `ReadOnlyLoopRequest`, `ReadOnlyLoopResult`, `LoopPassRecord`, `SufficiencyDecision`, `ClaimSupport`, and typed stop reasons.
- [ ] Tests must prove every result has a stop reason and sufficiency output.

## Task 2: Deterministic Sufficiency

- [ ] Implement `DeterministicSufficiencyChecker`.
- [ ] It should mark evidence sufficient when candidate and context-block thresholds are met.
- [ ] It should return missing reasons when evidence is absent or thin.
- [ ] It must not call an LLM.

## Task 3: Repetition Guard

- [ ] Implement top-N candidate overlap comparison.
- [ ] A pass is repeated when overlap is greater than or equal to `0.8` and sufficiency score has not improved.
- [ ] Tests must cover repeated and non-repeated evidence sets.

## Task 4: Read-Only Loop Runtime

- [ ] Implement `ReadOnlyMultipassLoop.run()`.
- [ ] It must call `index.validate`, `evidence.retrieve`, `evidence.rank`, and `context.build`.
- [ ] It must stop on `sufficient`, `empty_evidence`, `repeated_state`, `budget_exhausted`, or `service_failed`.
- [ ] It must append ledger events for run start, pass start, service completion/failure, sufficiency decision, and loop completion.

## Task 5: Grounded Response Metadata

- [ ] Build a deterministic `response_text` from selected context blocks.
- [ ] Build a `ClaimSupport` tuple where each block-backed statement cites at least one evidence id.
- [ ] Do not synthesize unsupported repository behavior claims.

## Task 6: Verification

- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_read_only_loop.py -q`.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/unit/v4 -q`.
- [ ] Run the v3 import boundary test.
- [ ] Run `compileall` for `src/homllm_v4` and `tests/unit/v4`.

## Completion Criteria

- The read-only multipass loop can stop because evidence is sufficient.
- It can stop because repeated evidence prevents useful progress.
- It can stop because budget is exhausted.
- It can stop on service failure with a visible error.
- Every loop result contains a stop reason and sufficiency decision.
- No new v3 imports exist outside adapters.
