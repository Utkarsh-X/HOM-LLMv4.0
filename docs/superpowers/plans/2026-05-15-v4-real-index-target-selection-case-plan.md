# V4 Real-Index Target-Selection Case Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real-index provider patch benchmark case that omits `target_file` from provider-proposed planning so target selection is exercised through the CLI benchmark path.

**Architecture:** Keep `RealIndexProviderPatchCase.target_file` as the expected provider/edit target for fixture setup and fake-provider content generation, but add `planner_target_file`. Existing cases set `planner_target_file=target_file`; one new semantic case sets `planner_target_file=None`, causing `ProviderProposedPatchPlanner` to retrieve broadly and select the target from evidence.

**Tech Stack:** Python dataclasses, pytest, HOM-LLM v4 real-index provider suite, `ProviderProposedPatchPlanner`.

---

### Task 1: Add Failing Benchmark Test

**Files:**
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [ ] **Step 1: Make fake retrieval handle omitted target**

In `FakeRetrievalService.retrieve`, resolve:

```python
        target_file = request.target_files[0] if request.target_files else "utils/string_tools.py"
```

This lets the injected planner test simulate broad retrieval for the new target-selection case.

- [ ] **Step 2: Assert target-selection case exists and verifies**

In the existing multi-case test, add:

```python
    selection_case = next(
        case for case in result.case_results if case.case_id == "string-truncate-guard-target-selection"
    )
    assert selection_case.actual_stop_reason == "verified"
```

Also assert the patched target exists:

```python
    selection_target = (
        tmp_path
        / "work"
        / "real-index-provider-suite"
        / "cases"
        / "string-truncate-guard-target-selection"
        / "utils"
        / "string_tools.py"
    )
    assert "if max_length <= len(suffix):" in selection_target.read_text(encoding="utf-8")
```

- [ ] **Step 3: Run test to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_runs_multiple_cases_with_injected_planner -q
```

Expected: FAIL because the new case does not exist.

### Task 2: Implement Target-Selection Case Support

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`

- [ ] **Step 1: Add planner target field**

Change `RealIndexProviderPatchCase`:

```python
    planner_target_file: str | None = None
```

Because dataclass defaults must follow non-defaults, keep it after `verification_mode`.

- [ ] **Step 2: Add target-selection case**

Append:

```python
    RealIndexProviderPatchCase(
        case_id="string-truncate-guard-target-selection",
        target_file="utils/string_tools.py",
        query="utils string_tools truncate_string max_length suffix guard",
        intent=(
            "Fix truncate_string so max_length shorter than suffix never returns "
            "a string longer than max_length."
        ),
        expected_behavior=(
            "truncate_string('abcdef', 2) returns 'ab' and "
            "truncate_string('abcdef', 4) returns 'a...'."
        ),
        provider_mode="truncate_guard",
        verification_mode="truncate_guard",
        planner_target_file=None,
    ),
```

- [ ] **Step 3: Preserve existing default behavior**

Add helper:

```python
def _planner_target_file(case: RealIndexProviderPatchCase | EvaluationCase) -> str | None:
    value = case.planner_target_file if isinstance(case, RealIndexProviderPatchCase) else case.input_payload.get("planner_target_file")
    if value == "":
        return None
    return value if isinstance(value, str) else None
```

For existing cases, set payload `planner_target_file` to `case.planner_target_file if case.planner_target_file is not None else case.target_file`.

- [ ] **Step 4: Pass planner target into request**

In `ProviderProposedPatchPlanRequest`, use:

```python
                target_file=_planner_target_file(case),
```

where `case` is the `EvaluationCase`.

- [ ] **Step 5: Include metadata**

Add `planner_target_file` to `real_index_provider_patch_case_metadata`.

- [ ] **Step 6: Run suite tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: all tests pass.

### Task 3: Verify CLI and Full Gates

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Run focused CLI target-selection case**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_target_selection --artifact-root temp\v4_real_index_provider_patch_runs_target_selection --run-id real-index-provider-patch-target-selection-check --case-id string-truncate-guard-target-selection --smoke-safe
```

Expected: `1 passed_cases`, `0 failed_cases`, `baseline_case_count=1`.

- [ ] **Step 2: Run full real-index benchmark**

Run the full `eval-real-index-provider-patch` CLI with fresh target and artifact roots.

Expected: all cases pass and semantic baseline count includes the new semantic target-selection case.

- [ ] **Step 3: Run full gates**

Run v4 tests, full unit tests, compileall, and forbidden v3 import scan.

- [ ] **Step 4: Update audits**

Record that a target-omitted real-index benchmark case exists. Keep remaining gap: only one target-omitted case, not broad autonomous task routing.
