# V4 Quality Dimension Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make quality-relevant evaluation dimensions explicit in real-index provider suite metrics so summaries do not over-focus on token counts.

**Architecture:** Add case-level categorical metrics at the real-index suite layer, not in the generic harness. These metrics describe the evaluation case and baseline comparability: whether localization is required, whether a behavior verification is used, whether the baseline was target-known, and what provider/verification modes are under test.

**Tech Stack:** HOM-LLM v4 evaluation suite, categorical summary metrics, pytest.

---

### Task 1: Add Quality Metrics To Case Results

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
- Test: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [x] **Step 1: Write failing quality metrics test**

Add a test running two cases: `admin-routes-noop` and `cache-namespace-invalidate-target-selection`. Assert:

```python
counts = result.summary_metrics["categorical_metric_counts"]
assert counts["quality_requires_localization"] == {"False": 1, "True": 1}
assert counts["quality_verification_kind"] == {"behavior": 1, "compile": 1}
assert counts["quality_provider_mode"] == {
    "cache_namespace_invalidation": 1,
    "noop": 1,
}
```

- [x] **Step 2: Run test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_records_quality_dimension_metrics -q
```

Expected before implementation: missing categorical keys.

- [x] **Step 3: Implement quality metric injection**

Add helper `_case_quality_metrics(case, planner_context_mode, direct_provider_target_source)` returning:

- `quality_requires_localization`: `True` when `_evaluation_planner_target_file(case) is None`
- `quality_verification_kind`: `"compile"` for compile cases, otherwise `"behavior"`
- `quality_provider_mode`: provider mode string
- `quality_verification_mode`: verification mode string
- `quality_baseline_target_knowledge`: `"target_known"` for direct-provider actual mode, `"target_unavailable"` for direct-provider planner mode, `"retrieval_localizes"` for retrieval mode

Merge this into every candidate case result metric dictionary.

- [x] **Step 4: Run quality metrics test and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_records_quality_dimension_metrics -q
```

Expected: pass.

### Task 2: Verify And Record

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/superpowers/plans/2026-05-16-v4-quality-dimension-metrics-plan.md`

- [x] **Step 1: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_direct_provider_patch_planner.py -q
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

Expected: pass/no forbidden imports.

- [x] **Step 3: Run quality-summary CLI smoke**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_quality_metrics --artifact-root temp\v4_real_index_provider_patch_runs_quality_metrics --run-id real-index-provider-patch-quality-metrics-check --case-id admin-routes-noop --case-id cache-namespace-invalidate-target-selection --smoke-safe
```

Expected: summary JSON includes the quality categorical metrics.

- [x] **Step 4: Update audits**

Record that evaluation summaries now expose quality dimensions before token metrics.
