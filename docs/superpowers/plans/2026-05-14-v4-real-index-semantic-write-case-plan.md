# v4 Real-Index Semantic Write Case Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the real-index provider write benchmark beyond no-op patches with one deterministic semantic edit verified by a focused behavior assertion.

**Architecture:** Reuse `run_real_index_provider_patch_suite`; add one case for `utils/string_tools.py::truncate_string` where the fake provider returns a non-no-op patch. The verification command must prove behavior, not only syntax.

**Tech Stack:** Python, pytest, v4 benchmark suite, v4 write/verify loop, real v3 retrieval adapter for CLI smoke.

---

## File Structure

- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
  - Add semantic case metadata and content transformation.
  - Allow per-case verification argv.
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`
  - Assert the semantic case runs and writes the expected guard.
- Modify audits:
  - `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - `docs/v4_architecture/09-active-goal-completion-audit.md`

---

### Task 1: Add Failing Semantic Case Test

**Files:**
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [ ] **Step 1: Tighten benchmark expectations**

Change:

```python
assert result.total_cases >= 3
```

to:

```python
assert result.total_cases >= 4
```

Add:

```python
semantic_target = (
    tmp_path
    / "work"
    / "real-index-provider-suite"
    / "cases"
    / "string-truncate-guard"
    / "utils"
    / "string_tools.py"
)
assert "if max_length <= len(suffix):" in semantic_target.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_runs_multiple_cases_with_injected_planner -q
```

Expected: FAIL because current suite has only three no-op cases.

---

### Task 2: Add Semantic Benchmark Case

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`

- [ ] **Step 1: Extend case dataclass**

Add:

```python
provider_mode: str = "noop"
verification_mode: str = "compile"
```

- [ ] **Step 2: Add semantic case**

Add case:

```python
RealIndexProviderPatchCase(
    case_id="string-truncate-guard",
    target_file="utils/string_tools.py",
    query="truncate_string max_length shorter than suffix edge case",
    intent="Fix truncate_string so max_length shorter than suffix never returns a string longer than max_length.",
    expected_behavior="truncate_string('abcdef', 2) returns 'ab' and truncate_string('abcdef', 4) returns 'a...'.",
    provider_mode="truncate_guard",
    verification_mode="truncate_guard",
)
```

- [ ] **Step 3: Add content transform**

Implement:

```python
def _provider_content(case: EvaluationCase, target_content: str) -> str:
    if case.input_payload.get("provider_mode") == "truncate_guard":
        old = "    if len(text) <= max_length:\n        return text\n    return text[:max_length - len(suffix)] + suffix"
        new = "    if len(text) <= max_length:\n        return text\n    if max_length <= len(suffix):\n        return text[:max_length]\n    return text[:max_length - len(suffix)] + suffix"
        if old not in target_content:
            raise ValueError("truncate_guard_pattern_not_found")
        return target_content.replace(old, new)
    return target_content
```

- [ ] **Step 4: Add verification argv selector**

Implement:

```python
def _verification_argv(case: EvaluationCase, target_file: str) -> tuple[str, ...]:
    if case.input_payload.get("verification_mode") == "truncate_guard":
        return (
            sys.executable,
            "-c",
            "from utils.string_tools import truncate_string; "
            "raise SystemExit(0 if truncate_string('abcdef', 2) == 'ab' "
            "and truncate_string('abcdef', 4) == 'a...' else 1)",
        )
    return (sys.executable, "-m", "compileall", "-q", target_file)
```

- [ ] **Step 5: Re-run targeted test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: pass.

---

### Task 3: Verification and Audit

- [ ] **Step 1: Run real-index CLI benchmark with fresh names**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_semantic --artifact-root temp\v4_real_index_provider_patch_runs_semantic --run-id real-index-provider-patch-semantic-check --smoke-safe
```

Expected: `4 passed_cases`, `0 failed_cases`.

- [ ] **Step 2: Run full verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

- [ ] **Step 3: Update audits**

Record that the real-index benchmark now has three no-op cases and one semantic non-no-op behavior-verified case.

---

## Self-Review

Spec coverage:

- This plan directly closes the weak "no-op only" benchmark gap with one deterministic semantic patch.
- It still avoids live provider calls and autonomous target selection.

Placeholder scan:

- No placeholder tasks remain.

Type consistency:

- The plan uses the existing suite function, case dataclass, and evaluation harness.

