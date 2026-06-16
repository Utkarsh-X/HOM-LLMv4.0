# v4 Retrieval-Backed Patch Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect v4 retrieval and direct-read services to the evidence-backed patch planner.

**Architecture:** Add a small orchestration service that accepts a patch planning request, retrieves evidence through `EvidenceRetrievalService`, direct-reads the target file through `DirectReadService`, then delegates to `EvidenceBackedPatchPlanner`. The orchestrator does not synthesize edits. It only turns retrieval evidence and fresh file reads into a validated patch plan result.

**Tech Stack:** Python dataclasses, existing v4 services/contracts, pytest.

---

## Files

Create:

- `src/homllm_v4/planning/retrieval_patch_planner.py`
- `tests/unit/v4/test_retrieval_patch_planner.py`

Modify:

- `src/homllm_v4/planning/__init__.py`

## Task 1: Orchestrator Contract

- [ ] Define `RetrievalBackedPatchPlanRequest` with:
  - `task_id`
  - `workspace_root`
  - `query`
  - `task_class`
  - `index_id`
  - `target_file`
  - `intent`
  - `expected_behavior`
  - `new_content`
  - `verification_argv`
  - `retrieval_policy`
  - `expected_content_hash`

## Task 2: Retrieval-Backed Planner

- [ ] Write a test where a fake retrieval adapter returns target-file evidence and the planner returns a patch plan.
- [ ] Write a test where retrieval succeeds but target evidence is missing and the planner returns `missing_target_evidence`.
- [ ] Write a test where direct read fails and the planner returns the direct read error code.
- [ ] Implement `RetrievalBackedPatchPlanner.plan(...)`.
- [ ] Return `CapabilityResult[EvidenceBackedPatchPlanResult]`.

## Task 3: Verification

- [ ] Run `pytest tests/unit/v4/test_retrieval_patch_planner.py -q`.
- [ ] Run `pytest tests/unit/v4/test_evidence_patch_planner.py -q`.
- [ ] Run `pytest tests/unit/v4 -q`.
- [ ] Run `pytest tests/unit -q`.
- [ ] Run compileall and smoke checks.

## Explicit Exclusions

- No LLM edit synthesis.
- No automatic target-file selection.
- No ranking/context packing inside this orchestrator.
- No write execution inside this orchestrator.
- No real benchmark expansion.
