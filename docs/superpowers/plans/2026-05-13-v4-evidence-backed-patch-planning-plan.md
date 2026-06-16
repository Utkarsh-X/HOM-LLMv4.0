# v4 Evidence-Backed Patch Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first bounded bridge from RAG/direct-read evidence to write-verify patch requests.

**Architecture:** This is not LLM patch generation. A deterministic planner validates that the target file appears in the evidence set, that a fresh direct read exists for the same file, and that the patch expected hash matches fresh content before constructing `PatchApplyRequest` and verification commands. Later LLM planners may propose `new_content`, but this runtime layer owns evidence validation and request construction.

**Tech Stack:** Python dataclasses, existing v4 evidence/patch/command/write-loop contracts, pytest.

---

## Files

Create:

- `src/homllm_v4/contracts/patch_plan.py`
- `src/homllm_v4/planning/__init__.py`
- `src/homllm_v4/planning/evidence_patch_planner.py`
- `tests/unit/v4/test_evidence_patch_planner.py`

Modify:

- `src/homllm_v4/evaluation/fixture_suites.py`

## Task 1: Patch Plan Contracts

- [ ] Add `PatchPlan` and `EvidenceBackedPatchPlanResult`.
- [ ] `PatchPlan` must include `patch_plan_id`, `task_id`, `intent`, `target_files`, `evidence_ids`, `expected_behavior`, `verification_gates`, `risk_flags`, and `user_visible_summary`.
- [ ] `EvidenceBackedPatchPlanResult` must include `patch_plan`, `patch_request`, and `verification_commands`.

## Task 2: Deterministic Planner

- [ ] Write tests proving the planner creates a patch request only when evidence and fresh direct read agree.
- [ ] Write tests proving it rejects missing target evidence.
- [ ] Write tests proving it rejects stale or hash-mismatched direct reads.
- [ ] Implement `EvidenceBackedPatchPlanner.plan(...)`.
- [ ] Return `CapabilityResult[EvidenceBackedPatchPlanResult]`.

## Task 3: Fixture Suite Integration

- [x] Modify `run_python_patch_fixture_suite(...)` so each case constructs a local `EvidenceSet` and `DirectReadResult` from the copied fixture workspace.
- [x] Use `EvidenceBackedPatchPlanner` to create `WriteVerifyLoopRequest`.
- [x] Keep existing case outcomes unchanged by converting planner failures into structured `CaseExecutionResult` values.

## Task 4: Verification

- [ ] Run `pytest tests/unit/v4/test_evidence_patch_planner.py -q`.
- [ ] Run `pytest tests/unit/v4/test_fixture_suite_runner.py tests/unit/v4/test_patch_case_evaluation.py -q`.
- [ ] Run `pytest tests/unit/v4 -q`.
- [ ] Run `pytest tests/unit -q`.
- [ ] Run compileall and smoke checks.

## Explicit Exclusions

- No LLM patch generation.
- No multi-file patch planning.
- No retrieval execution inside the planner.
- No automatic test discovery.
- No repair patch generation.
