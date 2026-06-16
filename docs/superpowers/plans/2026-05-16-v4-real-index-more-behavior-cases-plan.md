# v4 Real-Index More Behavior Cases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the real-index fake-provider write benchmark with two additional behavior-verified semantic patch cases outside the current string/validator-heavy coverage.

**Architecture:** Keep the benchmark offline and deterministic. Add two `RealIndexProviderPatchCase` entries, fake-provider patch modes, and focused Python verification commands; the existing v4 retrieval/planning/write/verify/evaluation path remains unchanged.

**Tech Stack:** Python, pytest, existing `eval-real-index-provider-patch` CLI/API.

---

## File Structure

- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
  - Add `parse-date-strip` case for `utils/date_helpers.py`.
  - Add `job-queue-total-size-guard` case for `async_jobs/job_queue.py`.
  - Add fake provider transformations and verification commands.
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`
  - Add assertions that the new cases run, baseline-fail, patch-verify, and mutate the copied case workspaces as expected.
- Modify after verification: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - Record the expanded benchmark count and evidence.
- Modify after verification: `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Record the expanded coverage and remaining live-provider gap.

---

### Task 1: Red Test For Additional Behavior Cases

**Files:**
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [ ] **Step 1: Add assertions for the new cases**

In `test_real_index_provider_patch_suite_runs_multiple_cases_with_injected_planner`, update the expected baseline count and add checks:

```python
date_target = (
    tmp_path
    / "work"
    / "real-index-provider-suite"
    / "cases"
    / "parse-date-strip"
    / "utils"
    / "date_helpers.py"
)
assert "datetime.strptime(date_string.strip(), format_str)" in date_target.read_text(encoding="utf-8")
job_queue_target = (
    tmp_path
    / "work"
    / "real-index-provider-suite"
    / "cases"
    / "job-queue-total-size-guard"
    / "async_jobs"
    / "job_queue.py"
)
assert "current_queue_size = sum(len(jobs) for jobs in self.pending_jobs.values())" in job_queue_target.read_text(encoding="utf-8")
assert result.summary_metrics["baseline_case_count"] == 8
date_case = next(case for case in result.case_results if case.case_id == "parse-date-strip")
assert date_case.baseline_stop_reason == "verification_failed"
assert date_case.actual_stop_reason == "verified"
job_case = next(case for case in result.case_results if case.case_id == "job-queue-total-size-guard")
assert job_case.baseline_stop_reason == "verification_failed"
assert job_case.actual_stop_reason == "verified"
```

- [ ] **Step 2: Run test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_runs_multiple_cases_with_injected_planner -q
```

Expected: failure because the new case workspaces do not exist and baseline count is still `6`.

---

### Task 2: Add Benchmark Cases And Fake Provider Patches

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`

- [ ] **Step 1: Add `parse-date-strip` case**

Add to `REAL_INDEX_PROVIDER_PATCH_CASES`:

```python
RealIndexProviderPatchCase(
    case_id="parse-date-strip",
    target_file="utils/date_helpers.py",
    query="utils date_helpers parse_date strips surrounding whitespace",
    intent="Make parse_date tolerate leading and trailing whitespace before parsing.",
    expected_behavior="parse_date(' 2024-01-02 ') returns a datetime and parse_date('bad') returns None.",
    provider_mode="parse_date_strip",
    verification_mode="parse_date_strip",
),
```

- [ ] **Step 2: Add `job-queue-total-size-guard` case**

Add:

```python
RealIndexProviderPatchCase(
    case_id="job-queue-total-size-guard",
    target_file="async_jobs/job_queue.py",
    query="async_jobs job_queue max_queue_size counts total pending jobs",
    intent="Make JobQueue enforce max_queue_size using total queued jobs, not priority bucket count.",
    expected_behavior="A queue with max_queue_size=2 rejects the third queued job.",
    provider_mode="job_queue_size_guard",
    verification_mode="job_queue_size_guard",
),
```

- [ ] **Step 3: Add fake provider transformations**

In `_provider_content`, add:

```python
if case.input_payload.get("provider_mode") == "parse_date_strip":
    old = "        return datetime.strptime(date_string, format_str)"
    new = "        return datetime.strptime(date_string.strip(), format_str)"
    if old not in target_content:
        raise ValueError("parse_date_strip_pattern_not_found")
    return target_content.replace(old, new)
if case.input_payload.get("provider_mode") == "job_queue_size_guard":
    old = (
        "            if len(self.pending_jobs) >= self.max_queue_size:\n"
        "                raise RuntimeError(f\"Queue full (max {self.max_queue_size})\")"
    )
    new = (
        "            current_queue_size = sum(len(jobs) for jobs in self.pending_jobs.values())\n"
        "            if current_queue_size >= self.max_queue_size:\n"
        "                raise RuntimeError(f\"Queue full (max {self.max_queue_size})\")"
    )
    if old not in target_content:
        raise ValueError("job_queue_size_guard_pattern_not_found")
    return target_content.replace(old, new)
```

- [ ] **Step 4: Add verification commands**

In `_verification_argv`, add:

```python
if case.input_payload.get("verification_mode") == "parse_date_strip":
    return (
        sys.executable,
        "-c",
        "from utils.date_helpers import parse_date; "
        "raise SystemExit(0 if parse_date(' 2024-01-02 ') is not None "
        "and parse_date('bad') is None else 1)",
    )
if case.input_payload.get("verification_mode") == "job_queue_size_guard":
    return (
        sys.executable,
        "-c",
        "from async_jobs.job_queue import JobQueue; "
        "JobQueue._instance = None; q = JobQueue(max_queue_size=2); "
        "q.enqueue('a', {}); q.enqueue('b', {}); ok = False\n"
        "try:\n"
        "    q.enqueue('c', {})\n"
        "except RuntimeError:\n"
        "    ok = True\n"
        "raise SystemExit(0 if ok else 1)",
    )
```

- [ ] **Step 5: Run targeted test and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_runs_multiple_cases_with_injected_planner -q
```

Expected: the targeted benchmark suite test passes.

---

### Task 3: Full Verification And Audit Update

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Run targeted real-index suite tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: all real-index suite tests pass.

- [ ] **Step 2: Run v4 tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
```

Expected: v4 tests pass.

- [ ] **Step 3: Run full unit suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
```

Expected: unit suite passes.

- [ ] **Step 4: Run compile and boundary checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected: compile exits `0`; boundary scan has no output.

- [ ] **Step 5: Run CLI benchmark**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_more_behavior --artifact-root temp\v4_real_index_provider_patch_runs_more_behavior --run-id real-index-provider-patch-more-behavior-check --smoke-safe
```

Expected:
- `passed_cases=11`
- `failed_cases=0`
- `baseline_case_count=8`
- `stop_reason_counts={"verified":11}`

- [ ] **Step 6: Update audits**

Record:
- real-index fake-provider benchmark has 11 cases;
- semantic behavior baselines increased from 6 to 8;
- new coverage touches `utils/date_helpers.py` and `async_jobs/job_queue.py`.

---

## Self-Review

Spec coverage:
- This expands benchmark coverage without adding live API cost or runtime authority.
- The cases are behavior-verified and baseline-checked, not compile-only no-ops.

Placeholder scan:
- No placeholders or deferred implementation steps are present.

Type consistency:
- New `provider_mode` values map to `_provider_content`.
- New `verification_mode` values map to `_verification_argv`.
