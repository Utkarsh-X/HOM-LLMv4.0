# V4 Provider Verification Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded provider repair slice that retries provider patch planning once after verification failure or timeout using explicit verification-failure context.

**Architecture:** Keep `WriteVerifyLoop` deterministic and LLM-free. The real-index evaluation runner owns repair orchestration: run provider planning, apply+verify once, inspect the stop reason, and if repair is enabled and the stop reason is repairable, call provider planning again against the current copied workspace with a `repair_context` string before a second apply+verify attempt. Metrics must expose repair attempts and aggregate provider token usage from both planning calls.

**Tech Stack:** HOM-LLM v4 dataclass contracts, `ProviderBackedEditProposer`, `ProviderProposedPatchPlanner`, `run_real_index_provider_patch_suite`, pytest.

---

### Task 1: Add Repair Context To Provider Prompts

**Files:**
- Modify: `src/homllm_v4/contracts/edit_proposal.py`
- Modify: `src/homllm_v4/planning/provider_edit_proposer.py`
- Modify: `src/homllm_v4/planning/provider_patch_planner.py`
- Test: `tests/unit/v4/test_provider_edit_proposer.py`
- Test: `tests/unit/v4/test_provider_patch_planner.py`

- [x] **Step 1: Write failing proposer prompt test**

Add this test to `tests/unit/v4/test_provider_edit_proposer.py`:

```python
def test_provider_backed_edit_proposer_includes_repair_context_in_prompt() -> None:
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Repair verification failure.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    request = EditProposalRequest(
        task_id="task-1",
        target_file="calculator.py",
        intent="fix add",
        expected_behavior="add returns a sum",
        current_content="def add(a, b):\n    return a - b\n",
        evidence_ids=("cand-1",),
        allowed_file_paths=("calculator.py",),
        verification_summary="pytest . -q",
        repair_context="Previous verification failed with exit_code=1.",
    )

    result = ProviderBackedEditProposer(provider=provider).propose(request)

    assert result.ok is True
    assert provider.last_request is not None
    assert "Repair context: Previous verification failed with exit_code=1." in (
        provider.last_request.prompt
    )
```

- [x] **Step 2: Run proposer prompt test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py::test_provider_backed_edit_proposer_includes_repair_context_in_prompt -q
```

Expected before implementation: fail because `EditProposalRequest` does not accept `repair_context`.

- [x] **Step 3: Implement repair context contract and prompt line**

Add `repair_context: str = ""` to `EditProposalRequest`. In `_build_edit_proposal_prompt_with_metadata`, include:

```python
*(("Repair context: " + request.repair_context,) if request.repair_context else ()),
```

between `Expected behavior:` and `Evidence IDs:`.

- [x] **Step 4: Run proposer prompt test and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py::test_provider_backed_edit_proposer_includes_repair_context_in_prompt -q
```

Expected: pass.

- [x] **Step 5: Write failing planner handoff test**

Add this test to `tests/unit/v4/test_provider_patch_planner.py`:

```python
def test_provider_proposed_patch_planner_passes_repair_context_to_provider(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Repair verification failure.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    planner = ProviderProposedPatchPlanner(
        retrieval_service=FakeRetrievalService(),
        direct_read_service=DirectReadService(workspace_root=tmp_path),
        edit_proposer=ProviderBackedEditProposer(provider=provider),
    )
    plan_request = request(tmp_path)
    plan_request = ProviderProposedPatchPlanRequest(
        task_id=plan_request.task_id,
        workspace_root=plan_request.workspace_root,
        query=plan_request.query,
        task_class=plan_request.task_class,
        index_id=plan_request.index_id,
        target_file=plan_request.target_file,
        intent=plan_request.intent,
        expected_behavior=plan_request.expected_behavior,
        verification_argv=plan_request.verification_argv,
        retrieval_policy=plan_request.retrieval_policy,
        expected_content_hash=plan_request.expected_content_hash,
        repair_context="Previous verification failed with exit_code=1.",
    )

    result = planner.plan(plan_request)

    assert result.ok is True
    assert provider.last_request is not None
    assert "Repair context: Previous verification failed with exit_code=1." in (
        provider.last_request.prompt
    )
```

- [x] **Step 6: Run planner handoff test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_patch_planner.py::test_provider_proposed_patch_planner_passes_repair_context_to_provider -q
```

Expected before implementation: fail because `ProviderProposedPatchPlanRequest` does not accept `repair_context`.

- [x] **Step 7: Implement planner repair context field**

Add `repair_context: str = ""` to `ProviderProposedPatchPlanRequest` and pass it into `EditProposalRequest(repair_context=request.repair_context)`.

- [x] **Step 8: Run planner handoff test and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_patch_planner.py::test_provider_proposed_patch_planner_passes_repair_context_to_provider -q
```

Expected: pass.

### Task 2: Add Bounded Repair To Real-Index Provider Suite

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
- Modify: `src/homllm_v4/cli.py`
- Test: `tests/unit/v4/test_real_index_provider_patch_suite.py`
- Test: `tests/unit/v4/test_provider_fixture_cli.py`

- [x] **Step 1: Write failing suite repair test**

Add a fake provider/planner test to `tests/unit/v4/test_real_index_provider_patch_suite.py` where the first provider response changes `truncate_string` incorrectly and the second response uses the correct `if max_length <= len(suffix)` guard. Run `run_real_index_provider_patch_suite(..., case_ids=("string-truncate-guard",), provider_repair_attempts=1)` and assert `passed_cases == 1`, `patch_attempt_count == 2`, `provider_repair_attempt_count == 1`, and provider token totals include both provider calls.

- [x] **Step 2: Run suite repair test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_repairs_after_verification_failure -q
```

Expected before implementation: fail because `provider_repair_attempts` is unsupported.

- [x] **Step 3: Implement suite-level repair orchestration**

In `run_real_index_provider_patch_suite`, add `provider_repair_attempts: int = 0`. After a failed/timeout `WriteVerifyLoop` result, if attempts remain, build repair context from stop reason and verification results, re-plan with `repair_context`, then run the write-verify loop again. Aggregate metrics from both plan results:

```text
provider_tokens_in = sum(plan token inputs)
provider_tokens_out = sum(plan token outputs)
provider_repair_attempt_count = repair attempts actually invoked
patch_attempt_count = total write-verify patch attempts across initial and repair runs
```

- [x] **Step 4: Run suite repair test and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_repairs_after_verification_failure -q
```

Expected: pass.

- [x] **Step 5: Add CLI flag propagation test**

Add a CLI test to `tests/unit/v4/test_provider_fixture_cli.py` asserting `--provider-repair-attempts 1` is passed into `run_real_index_provider_patch_suite`.

- [x] **Step 6: Run CLI flag test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_passes_provider_repair_attempts_to_real_index_provider_patch_suite -q
```

Expected before implementation: fail because the CLI argument is unsupported.

- [x] **Step 7: Implement CLI flag**

Add `--provider-repair-attempts` to `eval-real-index-provider-patch` with default `0`, and pass it to `run_real_index_provider_patch_suite` in normal and preflight paths.

- [x] **Step 8: Run CLI flag test and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_passes_provider_repair_attempts_to_real_index_provider_patch_suite -q
```

Expected: pass.

### Task 3: Verify And Document

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify: `docs/superpowers/plans/2026-05-16-v4-provider-verification-repair-plan.md`

- [x] **Step 1: Run focused provider/evaluation tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py tests\unit\v4\test_provider_patch_planner.py tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: all tests pass.

- [x] **Step 2: Run broader verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected: v4 and full unit suites pass, compileall exits `0`, and boundary scan prints no matches.

- [x] **Step 3: Update audits**

Record the repair-loop slice, tests, and remaining limitation: this is a bounded suite-level provider repair, not a general autonomous multi-step repair agent.
