# v4 Bounded Edit Proposal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first bounded model-edit proposal seam without allowing unbounded agentic writing.

**Architecture:** Runtime still owns retrieval, target files, fresh direct reads, allowed file scope, stale-context hashes, verification commands, and patch application. A proposal service may only produce replacement content or a structured edit for an already-approved single target file. The runtime validates the proposal through `EvidenceBackedPatchPlanner` and `WriteVerifyLoop`.

**Tech Stack:** Python dataclasses, existing v4 planning/write-verify contracts, injectable proposer callable for deterministic tests.

---

## Files

Create:

- `src/homllm_v4/contracts/edit_proposal.py`
- `src/homllm_v4/planning/bounded_edit_proposer.py`
- `tests/unit/v4/test_bounded_edit_proposer.py`

Modify:

- `src/homllm_v4/planning/__init__.py`

## Task 1: Proposal Contracts

- [ ] Add `EditProposalRequest`.
- [ ] Add `EditProposalResult`.
- [ ] Request must include:
  - `task_id`
  - `target_file`
  - `intent`
  - `expected_behavior`
  - `current_content`
  - `evidence_ids`
  - `allowed_file_paths`
  - `verification_summary`
- [ ] Result must include:
  - `target_file`
  - `new_content`
  - `rationale`
  - `evidence_ids`
  - `risk_flags`

## Task 2: Bounded Proposer

- [ ] Implement `BoundedEditProposer`.
- [ ] It accepts an injected proposer callable.
- [ ] It rejects proposals for files outside `allowed_file_paths`.
- [ ] It rejects proposals with empty `new_content`.
- [ ] It rejects proposals that drop all evidence ids.
- [ ] It returns `CapabilityResult[EditProposalResult]`.

## Task 3: Planner Integration Helper

- [ ] Add helper to convert an accepted `EditProposalResult` plus fresh evidence/read context into `EvidenceBackedPatchPlanRequest`.
- [ ] Do not execute patching in the proposer.
- [ ] Do not call LLMs in unit tests.

## Task 4: Verification

- [ ] Run `pytest tests/unit/v4/test_bounded_edit_proposer.py -q`.
- [ ] Run `pytest tests/unit/v4 -q`.
- [ ] Run `pytest tests/unit -q`.
- [ ] Run compileall and smoke checks.

## Explicit Exclusions

- No provider/API call wiring yet.
- No prompt engineering yet.
- No multi-file proposals.
- No automatic target selection.
- No patch execution inside proposer.
- No rollback.

## Promotion Gate

This milestone is successful only if a model/proposer can be safely boxed into:

```text
fixed target file + fixed evidence ids + fixed verification plan -> proposed new_content
```

The runtime must still be able to reject the proposal before any write.
