# V4 Direct Provider Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a same-provider direct-file baseline mode for the real-index provider patch suite, so HOM-LLM's retrieval/evidence-context path can be compared against a target-known provider prompt without retrieved evidence.

**Architecture:** Keep the existing retrieval-backed provider planner unchanged. Add a separate `DirectProviderPatchPlanner` that reads the supplied target file, calls `ProviderBackedEditProposer` with no retrieved evidence context, then passes the proposal through `EvidenceBackedPatchPlanner` using a synthetic direct-file evidence candidate. Expose this through `eval-real-index-provider-patch --planner-context-mode retrieval|direct-provider`; in direct-provider mode every case uses its known `target_file` so the comparison isolates evidence/context value rather than target-localization value.

**Tech Stack:** HOM-LLM v4 dataclasses, provider edit proposer, evidence-backed patch planner, real-index provider evaluation harness, pytest.

---

### Task 1: Add Direct Provider Planner

**Files:**
- Create: `src/homllm_v4/planning/direct_provider_patch_planner.py`
- Test: `tests/unit/v4/test_direct_provider_patch_planner.py`

- [x] **Step 1: Write failing success-path planner test**

Create `tests/unit/v4/test_direct_provider_patch_planner.py` with a fake provider that asserts the prompt contains `Evidence context: none supplied`, returns a full-file replacement, and verifies the planner returns a patch request for the supplied target file. Assert telemetry includes:

```python
assert result.telemetry.output_summary["planner_context_mode"] == "direct_provider"
assert result.telemetry.output_summary["target_selection_decision"] == "direct_supplied"
assert result.telemetry.output_summary["evidence_context_item_count"] == 0
```

- [x] **Step 2: Run success-path test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_direct_provider_patch_planner.py::test_direct_provider_patch_planner_builds_patch_without_retrieval_evidence -q
```

Expected before implementation: import failure for `DirectProviderPatchPlanner`.

- [x] **Step 3: Implement `DirectProviderPatchPlanner`**

Implement a planner with:

- input type: existing `ProviderProposedPatchPlanRequest`
- dependencies: `DirectReadService`, `ProviderBackedEditProposer`, optional `EvidenceBackedPatchPlanner`
- behavior:
  - require `request.target_file`; fail with `direct_provider_target_required` if absent
  - direct-read the target file with hash
  - call `ProviderBackedEditProposer.propose(...)` with `evidence_ids=()`, `evidence_context=()`, and allowed file set containing only the target
  - create a synthetic `EvidenceSet` with one `EvidenceCandidate` for the target file so existing evidence-backed patch planning remains the final safety gate
  - preserve original trailing newline like the retrieval-backed planner
  - add telemetry fields `planner_context_mode="direct_provider"`, `resolved_target_file`, and `target_selection_decision="direct_supplied"`

- [x] **Step 4: Run success-path test and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_direct_provider_patch_planner.py::test_direct_provider_patch_planner_builds_patch_without_retrieval_evidence -q
```

Expected: pass.

- [x] **Step 5: Add missing-target test**

Add a test where `target_file=None`; assert `ok=False`, `error.code == "direct_provider_target_required"`, and provider was not called.

- [x] **Step 6: Run planner tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_direct_provider_patch_planner.py -q
```

Expected: pass.

### Task 2: Wire Direct Baseline Mode Into Real-Index Suite And CLI

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
- Modify: `src/homllm_v4/cli.py`
- Test: `tests/unit/v4/test_real_index_provider_patch_suite.py`
- Test: `tests/unit/v4/test_provider_fixture_cli.py`

- [x] **Step 1: Write failing suite test**

Add a unit test that runs `run_real_index_provider_patch_suite(..., planner_context_mode="direct_provider", planner_builder=build_fake_planner, edit_provider_mode="fake", case_ids=("string-truncate-guard-target-selection",))`. Assert:

```python
assert result.passed_cases == 1
case = result.case_results[0]
assert case.metrics["planner_context_mode"] == "direct_provider"
assert case.metrics["target_selection_decision"] == "direct_supplied"
assert case.metrics["evidence_context_item_count"] == 0
assert case.metrics["resolved_target_file"] == "utils/string_tools.py"
```

- [x] **Step 2: Run suite test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_can_run_direct_provider_context_mode -q
```

Expected before implementation: unexpected keyword argument `planner_context_mode`.

- [x] **Step 3: Implement suite mode**

Add `planner_context_mode: str = "retrieval"` to `run_real_index_provider_patch_suite`.

Rules:

- accepted values: `"retrieval"` and `"direct_provider"`
- invalid values raise `ValueError("unsupported_planner_context_mode: <value>")`
- retrieval mode keeps current behavior
- direct-provider mode builds `DirectProviderPatchPlanner` internally and ignores `planner_builder`
- direct-provider mode passes `target_file=case.input_payload["target_file"]` to `ProviderProposedPatchPlanRequest` even for target-selection cases

- [x] **Step 4: Run suite test and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_can_run_direct_provider_context_mode -q
```

Expected: pass.

- [x] **Step 5: Write failing CLI propagation test**

Add a CLI test that monkeypatches `run_real_index_provider_patch_suite`, invokes:

```python
main([
    "eval-real-index-provider-patch",
    "--config", "cfg.yaml",
    "--source-workspace-root", "repo",
    "--workspace-root", "work",
    "--artifact-root", "runs",
    "--planner-context-mode", "direct-provider",
])
```

Assert the captured call receives `planner_context_mode == "direct_provider"`.

- [x] **Step 6: Run CLI test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_passes_direct_provider_planner_context_mode -q
```

Expected before implementation: CLI parser rejects `--planner-context-mode`.

- [x] **Step 7: Implement CLI flag**

Add:

```python
real_index_provider_patch.add_argument(
    "--planner-context-mode",
    choices=("retrieval", "direct-provider"),
    default="retrieval",
)
```

Pass `planner_context_mode=args.planner_context_mode.replace("-", "_")` to normal and prompt-preflight suite calls.

- [x] **Step 8: Run CLI test and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_passes_direct_provider_planner_context_mode -q
```

Expected: pass.

### Task 3: Verify And Run Baseline

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/superpowers/plans/2026-05-16-v4-direct-provider-baseline-plan.md`

- [x] **Step 1: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_direct_provider_patch_planner.py tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_provider_fixture_cli.py -q
```

Expected: pass.

- [x] **Step 2: Run broad verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected: v4/full unit suites pass, compileall passes, boundary scan prints no matches.

- [x] **Step 3: Run direct-provider fake baseline smoke**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_direct_provider_fake13 --artifact-root temp\v4_real_index_provider_patch_runs_direct_provider_fake13 --run-id real-index-provider-patch-direct-provider-fake13-check --planner-context-mode direct-provider --smoke-safe
```

Expected: fake provider suite passes and summary shows `planner_context_mode={"direct_provider":13}` or equivalent categorical metrics.

- [x] **Step 4: Optionally run live direct-provider 13-case baseline**

Run only if API/network access is available:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_direct_provider_live13_preview --artifact-root temp\v4_real_index_provider_patch_runs_direct_provider_live13_preview --run-id real-index-provider-patch-direct-provider-live13-preview-check --planner-context-mode direct-provider --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --max-prompt-chars 22000 --provider-repair-attempts 1 --smoke-safe
```

Expected useful outcome: record pass/fail metrics as the same-provider direct-file baseline.

- [x] **Step 5: Update audits**

Record the direct-provider mode, fake smoke result, optional live baseline result, and the interpretation: this is an internal same-provider baseline, not an external coding-agent baseline.
