# V4 Provider Planner Selection Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface provider-proposed planner target-selection decisions in successful telemetry so omitted-target planning is inspectable after a run.

**Architecture:** Keep `EvidenceBackedPatchPlanResult` unchanged. `ProviderProposedPatchPlanner` wraps the final capability result with provider-planner telemetry containing whether the target was supplied or selected, the resolved target file, and selector scores when selection was used. Ambiguous selection already returns structured failure telemetry.

**Tech Stack:** Python dataclasses, pytest, HOM-LLM v4 `CapabilityResult`, `CapabilityTelemetry`.

---

### Task 1: Add Failing Telemetry Tests

**Files:**
- Modify: `tests/unit/v4/test_provider_patch_planner.py`

- [ ] **Step 1: Assert selected-target telemetry**

In `test_provider_proposed_patch_planner_selects_target_file_from_retrieved_evidence`, add:

```python
    assert result.telemetry.output_summary["target_selection_decision"] == "selected"
    assert result.telemetry.output_summary["resolved_target_file"] == "calculator.py"
    assert result.telemetry.output_summary["candidate_file_scores"] == {"calculator.py": 1.0}
```

- [ ] **Step 2: Assert supplied-target telemetry**

In `test_provider_proposed_patch_planner_creates_patch_plan_from_retrieval_and_provider`, add:

```python
    assert result.telemetry.output_summary["target_selection_decision"] == "supplied"
    assert result.telemetry.output_summary["resolved_target_file"] == "calculator.py"
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_patch_planner.py -q
```

Expected: FAIL because successful planner telemetry currently comes from `EvidenceBackedPatchPlanner` and lacks selection fields.

### Task 2: Wrap Successful Planner Telemetry

**Files:**
- Modify: `src/homllm_v4/planning/provider_patch_planner.py`

- [ ] **Step 1: Track target selection result**

Inside `plan`, initialize:

```python
        selection: TargetFileSelectionResult | None = None
```

Use the same variable when target selection is performed.

- [ ] **Step 2: Wrap evidence-planner result**

Replace direct `return self.evidence_planner.plan(...)` with:

```python
        planned = self.evidence_planner.plan(...)
        return _with_provider_planner_telemetry(
            planned,
            request=request,
            resolved_target_file=target_file,
            selection=selection,
        )
```

- [ ] **Step 3: Add wrapper helper**

Add:

```python
def _with_provider_planner_telemetry(
    result: CapabilityResult[EvidenceBackedPatchPlanResult],
    *,
    request: ProviderProposedPatchPlanRequest,
    resolved_target_file: str,
    selection: TargetFileSelectionResult | None,
) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
    output_summary = dict(result.telemetry.output_summary)
    output_summary["resolved_target_file"] = resolved_target_file
    if selection is None:
        output_summary["target_selection_decision"] = "supplied"
    else:
        output_summary["target_selection_decision"] = selection.decision
        output_summary["candidate_file_scores"] = selection.candidate_file_scores
        output_summary["target_selection_confidence"] = selection.confidence

    return CapabilityResult(
        capability_name="patch.plan.provider_proposed",
        ok=result.ok,
        output=result.output,
        error=result.error,
        telemetry=CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=result.telemetry.duration_ms,
            input_summary={
                "task_id": request.task_id,
                "target_file_supplied": request.target_file is not None,
            },
            output_summary=output_summary,
            token_usage=result.telemetry.token_usage,
            model_usage=result.telemetry.model_usage,
            degraded=result.telemetry.degraded,
            degradation_reason=result.telemetry.degradation_reason,
        ),
        artifacts=result.artifacts,
    )
```

- [ ] **Step 4: Run planner tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_patch_planner.py -q
```

Expected: all planner tests pass.

### Task 3: Verify and Audit

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_patch_planner.py tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

- [ ] **Step 2: Run full gates**

Run v4 tests, full unit tests, compileall, and forbidden v3 import scan.

- [ ] **Step 3: Update audits**

Record that provider-proposed planner telemetry now distinguishes supplied targets from evidence-selected targets and includes selector scores for successful omitted-target plans.
