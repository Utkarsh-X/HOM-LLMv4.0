# V4 Provider Token Metrics Actual Invocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make real-index provider patch metrics report provider token usage only from actual provider telemetry, never from static provider object attributes.

**Architecture:** `ProviderBackedEditProposer` already records token usage only when a provider response exists. `ProviderProposedPatchPlanner` must preserve that token usage when converting proposal telemetry into patch-planner telemetry, and `run_real_index_provider_patch_suite` must aggregate token metrics from planner telemetry rather than reading provider attributes.

**Tech Stack:** Python, pytest, HOM-LLM v4 provider planning and evaluation harness.

---

### Task 1: Prompt-Cap Failure Reports Zero Provider Tokens

**Files:**
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
- Modify: `src/homllm_v4/planning/provider_patch_planner.py`

- [x] **Step 1: Strengthen the failing prompt-cap regression**

Add these assertions to `test_real_index_provider_patch_suite_prompt_limit_fails_before_provider_call`:

```python
assert case.metrics["provider_tokens_in"] == 0
assert case.metrics["provider_tokens_out"] == 0
assert result.summary_metrics["numeric_metric_totals"]["provider_tokens_in"] == 0
assert result.summary_metrics["numeric_metric_totals"]["provider_tokens_out"] == 0
```

- [x] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_prompt_limit_fails_before_provider_call -q
```

Expected: FAIL because `_case_result` currently reads static fake-provider `tokens_in/tokens_out` attributes even when prompt cap prevents provider invocation.

- [x] **Step 3: Preserve provider token usage in planner telemetry**

In `src/homllm_v4/planning/provider_patch_planner.py`, after provider proposal succeeds, capture:

```python
provider_token_usage = proposal.telemetry.token_usage if proposal.telemetry else {}
provider_model_usage = proposal.telemetry.model_usage if proposal.telemetry else {}
```

Pass both into `_with_provider_planner_telemetry`, and update the helper signature:

```python
def _with_provider_planner_telemetry(
    result: CapabilityResult[EvidenceBackedPatchPlanResult],
    *,
    request: ProviderProposedPatchPlanRequest,
    resolved_target_file: str,
    selection: TargetFileSelectionResult | None,
    provider_prompt_metrics: dict[str, object],
    provider_token_usage: dict[str, int],
    provider_model_usage: dict[str, object],
) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
```

Use those values in the returned telemetry:

```python
token_usage=provider_token_usage,
model_usage=provider_model_usage,
```

- [x] **Step 4: Aggregate provider tokens from planner telemetry**

In `_planner_metrics`, add:

```python
token_usage = plan_result.telemetry.token_usage
if token_usage:
    metrics["provider_tokens_in"] = int(token_usage.get("input", 0))
    metrics["provider_tokens_out"] = int(token_usage.get("output", 0))
```

In `_case_result`, remove static provider attribute reads and default to zero:

```python
"provider_tokens_in": 0,
"provider_tokens_out": 0,
```

Then `metrics.update(planner_metrics or {})` will overwrite zeros only when actual provider telemetry exists.

- [x] **Step 5: Run focused test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_prompt_limit_fails_before_provider_call -q
```

Expected: PASS.

- [x] **Step 6: Run provider planner and real-index suite tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_patch_planner.py tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: PASS.

- [x] **Step 7: Verify CLI failure metrics**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_prompt_limit_failure_tokens --artifact-root temp\v4_real_index_provider_patch_runs_prompt_limit_failure_tokens --run-id real-index-provider-patch-prompt-limit-failure-token-check --case-id admin-routes-noop --max-prompt-chars 10 --smoke-safe
```

Expected: exit code `1`, `provider_prompt_budget_exceeded`, and `provider_tokens_in/out` totals equal `0`.

- [x] **Step 8: Run final verification gates**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected: all pytest/compile commands pass, and the boundary scan prints no matches.
