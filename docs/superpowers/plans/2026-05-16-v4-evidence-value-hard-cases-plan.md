# V4 Evidence-Value Hard Cases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add harder real-index provider patch cases where target selection must distinguish nearby files and the task is not simply a path-explicit single-file edit.

**Architecture:** Extend the existing real-index provider patch suite with two target-omitted semantic cases. Keep runtime authority unchanged. Fake-provider cases remain deterministic; live provider runs stay optional. These cases are designed to challenge retrieval/target selection and expose whether the benchmark can demonstrate evidence value beyond target-known edits.

**Tech Stack:** HOM-LLM v4 real-index provider suite, copied `test_repo`, fake provider content modes, focused Python verification commands, pytest.

---

### Task 1: Add Hard Evidence-Value Cases

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
- Test: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [x] **Step 1: Write failing metadata/test for new hard cases**

Add a test asserting `REAL_INDEX_PROVIDER_PATCH_CASES` contains:

- `cache-namespace-invalidate-target-selection`
- `metrics-labelled-stats-target-selection`

Both cases must have `planner_target_file is None`, proving they exercise target selection rather than supplied target paths.

- [x] **Step 2: Run metadata test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_includes_hard_cache_target_selection_cases -q
```

Expected before implementation: fail because the cases do not exist.

- [x] **Step 3: Add case definitions**

Add two `RealIndexProviderPatchCase` entries:

1. `cache-namespace-invalidate-target-selection`
   - `target_file="cache/cache_manager.py"`
   - query: `"cache namespace invalidation clears all memory entries for a namespace"`
   - provider mode: `cache_namespace_invalidation`
   - verification mode: `cache_namespace_invalidation`
   - `planner_target_file=None`

2. `metrics-labelled-stats-target-selection`
   - `target_file="monitoring/metrics.py"`
   - query: `"labelled histogram timer stats appear in all metrics export"`
   - provider mode: `metrics_labelled_stats`
   - verification mode: `metrics_labelled_stats`
   - `planner_target_file=None`

- [x] **Step 4: Run metadata test and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_includes_hard_cache_target_selection_cases -q
```

Expected: pass.

### Task 2: Add Fake Provider Patches And Verification

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
- Test: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [x] **Step 1: Write failing fake-suite behavior test**

Add a test running `run_real_index_provider_patch_suite(..., planner_builder=build_fake_planner, case_ids=(new cases...))`. Assert:

```python
assert result.total_cases == 2
assert result.passed_cases == 2
assert result.summary_metrics["categorical_metric_counts"]["target_selection_decision"] == {"selected": 2}
assert resolved files include "cache/cache_manager.py" and "cache/decorators.py"
```

- [x] **Step 2: Run behavior test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_runs_hard_cache_target_selection_cases -q
```

Expected before provider/verification implementation: fail due missing provider modes or failing verification.

- [x] **Step 3: Implement provider content modes**

Add deterministic fake-provider transformations:

- `cache_namespace_invalidation`: change `CacheManager._generate_key` to return `f"{namespace}:{identifier}"` rather than an MD5 hash so namespace prefix invalidation can work.
- `metrics_labelled_stats`: make `MetricsCollector.get_all_metrics` compute histogram/timer stats directly from stored labelled metric buckets instead of stripping labels and re-querying without labels.

- [x] **Step 4: Implement verification modes**

Add verification commands:

- `cache_namespace_invalidation`: create `CacheManager`, reset singleton state, set two entries in one namespace, call `invalidate(namespace)`, assert both reads miss.
- `metrics_labelled_stats`: record a labelled histogram and timer, call `get_all_metrics`, and assert the labelled keys report `count == 1`.

- [x] **Step 5: Run behavior test and confirm GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_runs_hard_cache_target_selection_cases -q
```

Expected: pass.

### Task 3: Verify And Record

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/superpowers/plans/2026-05-16-v4-evidence-value-hard-cases-plan.md`

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

Expected: suites pass, compileall passes, boundary scan prints no matches.

- [x] **Step 3: Run fake hard-case CLI smoke**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_hard_evidence_fake --artifact-root temp\v4_real_index_provider_patch_runs_hard_evidence_fake --run-id real-index-provider-patch-hard-evidence-fake-check --case-id cache-namespace-invalidate-target-selection --case-id metrics-labelled-stats-target-selection --smoke-safe
```

Expected: `2 passed_cases`, `0 failed_cases`, `target_selection_decision={"selected":2}`.

- [x] **Step 4: Update audits**

Record that the suite now includes two harder cache target-selection cases. Do not claim this proves RAG superiority until live and baseline comparisons are run.
