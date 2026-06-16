# v4 M5 Fixture Patch Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first narrow Milestone 5 task class: deterministic small Python patch tasks evaluated through the v4 write-verify harness.

**Architecture:** Keep this as an evaluation layer, not a new agent brain. A frozen fixture repository supplies known files and tests. A small request builder translates an `EvaluationCase.input_payload` into a `WriteVerifyLoopRequest`, using existing `PatchApplyRequest`, `CommandRunRequest`, `WriteVerifyLoop`, and `V4EvaluationHarness`.

**Tech Stack:** Python dataclasses, pathlib/shutil, pytest, existing v4 contracts/services/runtime/evaluation.

---

## Files

Create:

- `fixtures/v4/python_patch_repo/calculator.py`
- `fixtures/v4/python_patch_repo/test_calculator.py`
- `src/homllm_v4/evaluation/patch_cases.py`
- `tests/unit/v4/test_patch_case_evaluation.py`

Modify:

- `src/homllm_v4/evaluation/__init__.py`

## Task 1: Frozen Fixture Repository

- [ ] **Step 1: Create fixture source file**

Create `fixtures/v4/python_patch_repo/calculator.py`:

```python
def add(a: int, b: int) -> int:
    return a - b
```

- [ ] **Step 2: Create fixture test file**

Create `fixtures/v4/python_patch_repo/test_calculator.py`:

```python
from calculator import add


def test_add_returns_sum() -> None:
    assert add(2, 3) == 5
```

- [ ] **Step 3: Run fixture test directly and verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest fixtures\v4\python_patch_repo -q
```

Expected: `1 failed`.

## Task 2: Patch Case Request Builder

- [ ] **Step 1: Write failing builder tests**

Add `tests/unit/v4/test_patch_case_evaluation.py` with tests that:

- copy `fixtures/v4/python_patch_repo` to `tmp_path / "repo"`
- create an `EvaluationCase` payload containing `file_path`, `expected_content_hash`, `new_content`, `allowed_file_paths`, and `verification_argv`
- assert the builder returns a `WriteVerifyLoopRequest`
- assert `PatchApplyRequest.allowed_file_paths` contains only `calculator.py`
- assert verification command cwd is `.`

- [ ] **Step 2: Run builder test and verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_patch_case_evaluation.py -q
```

Expected: import failure for `homllm_v4.evaluation.patch_cases`.

- [ ] **Step 3: Implement `patch_cases.py`**

Create `src/homllm_v4/evaluation/patch_cases.py` with:

```python
from pathlib import Path

from homllm_v4.contracts.command import CommandRunRequest
from homllm_v4.contracts.evaluation import EvaluationCase
from homllm_v4.contracts.patch import FilePatch, PatchApplyRequest
from homllm_v4.contracts.write_loop import WriteVerifyLoopRequest


def build_write_verify_request_from_case(case: EvaluationCase, *, workspace_root: Path, run_id: str) -> WriteVerifyLoopRequest:
    payload = case.input_payload
    file_path = _required_str(payload, "file_path")
    expected_hash = _optional_str(payload, "expected_content_hash")
    new_content = _required_str(payload, "new_content")
    verification_argv = _required_str_tuple(payload, "verification_argv")
    allowed_file_paths = _optional_str_tuple(payload, "allowed_file_paths")

    patch_request = PatchApplyRequest(
        task_id=case.case_id,
        workspace_root=str(workspace_root),
        patches=(FilePatch(file_path, expected_hash, new_content),),
        allowed_file_paths=allowed_file_paths,
        max_file_changes=1,
    )
    verification = CommandRunRequest(
        task_id=case.case_id,
        workspace_root=str(workspace_root),
        cwd=".",
        argv=verification_argv,
        timeout_seconds=10,
    )
    return WriteVerifyLoopRequest(
        task_id=case.case_id,
        run_id=run_id,
        workspace_root=str(workspace_root),
        patch_request=patch_request,
        verification_commands=(verification,),
        max_verification_commands=1,
        max_patch_attempts=1,
    )


def _required_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"missing string payload field: {key}")
    return value


def _optional_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"invalid string payload field: {key}")
    return value


def _required_str_tuple(payload: dict[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"missing string sequence payload field: {key}")
    return tuple(value)


def _optional_str_tuple(payload: dict[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"invalid string sequence payload field: {key}")
    return tuple(value)
```

- [ ] **Step 4: Export the builder**

Modify `src/homllm_v4/evaluation/__init__.py`:

```python
from homllm_v4.evaluation.patch_cases import build_write_verify_request_from_case

__all__ = ("build_write_verify_request_from_case",)
```

- [ ] **Step 5: Run builder tests and verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_patch_case_evaluation.py -q
```

Expected: pass.

## Task 3: End-to-End Fixture Evaluation

- [ ] **Step 1: Add end-to-end test**

Extend `tests/unit/v4/test_patch_case_evaluation.py` with a test that:

- copies `fixtures/v4/python_patch_repo` to a temp workspace
- builds a patch changing `return a - b` to `return a + b`
- constructs `WriteVerifyLoop` with `WorkspacePatchService`, `LocalCommandService`, `ArtifactManager`, and `EventWriter`
- runs `V4EvaluationHarness` with `make_write_verify_runner`
- asserts `passed_cases == 1`, `failed_cases == 0`, and `calculator.py` contains `return a + b`
- asserts `.homllm/runs/<run_id>/evaluation/summary.json` exists

- [ ] **Step 2: Run end-to-end test and verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_patch_case_evaluation.py -q
```

Expected: pass.

## Task 4: Verification Gate

- [ ] **Step 1: Run full v4 suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
```

Expected: all pass, existing intentional skip allowed.

- [ ] **Step 2: Run compile check**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py
```

Expected: no output and exit code `0`.

- [ ] **Step 3: Run boundary check**

Run:

```powershell
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected: no output.

- [ ] **Step 4: Run real v3 smoke**

Run:

```powershell
$env:HOMLLM_V4_RUN_REAL_V3_SMOKE='1'; .\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_read_only_loop_smoke -q -s
```

Expected: pass.

## Task 5: Safety Case Evaluation Hardening

- [ ] **Step 1: Add expected error-code semantics to harness tests**

Extend `tests/unit/v4/test_evaluation_harness.py` with a case where:

- `expected_stop_reason` is `patch_failed`
- `expected_error_code` is `stale_context`
- runner returns `CaseExecutionResult(stop_reason="patch_failed", error_code="stale_context", metrics={})`
- harness marks the case as passed

- [ ] **Step 2: Run harness test and verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_evaluation_harness.py -q
```

Expected: failure because `EvaluationCase` does not yet support `expected_error_code` and the harness treats any error code as failure.

- [ ] **Step 3: Implement expected error-code matching**

Modify `src/homllm_v4/contracts/evaluation.py`:

```python
@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    runner_id: str
    task_type: str
    input_payload: dict[str, object]
    expected_stop_reason: str
    expected_error_code: str | None = None
```

Modify `src/homllm_v4/evaluation/harness.py` so a case passes when:

```python
execution.stop_reason == case.expected_stop_reason
and execution.error_code == case.expected_error_code
```

- [ ] **Step 4: Add fixture safety suite test**

Extend `tests/unit/v4/test_patch_case_evaluation.py` with a test that runs four cases through `V4EvaluationHarness`:

- verified fix: expected stop `verified`, expected error `None`
- stale context block: expected stop `patch_failed`, expected error `stale_context`
- unexpected file block: expected stop `patch_failed`, expected error `diff_inspection_failed`
- repair budget exhausted: expected stop `repair_budget_exhausted`, expected error `None`

The test must assert:

- `total_cases == 4`
- `passed_cases == 4`
- `failed_cases == 0`
- `evaluation/summary.json` exists

- [ ] **Step 5: Add optional max patch attempts to patch case builder**

Modify `src/homllm_v4/evaluation/patch_cases.py` so `input_payload["max_patch_attempts"]` can override the default of `1`.

- [ ] **Step 6: Run safety suite test and verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_evaluation_harness.py tests\unit\v4\test_patch_case_evaluation.py -q
```

Expected: pass.

## Task 6: Measurement And Baseline Hooks

- [ ] **Step 1: Add run-level summary metric tests**

Extend `tests/unit/v4/test_evaluation_harness.py` to assert:

- stop reason counts are aggregated
- error code counts are aggregated
- numeric metric totals are aggregated
- numeric metric averages are aggregated

- [ ] **Step 2: Add baseline runner hook test**

Extend `tests/unit/v4/test_evaluation_harness.py` to assert:

- `EvaluationCase.baseline_runner_id` can point to another runner
- candidate and baseline metrics are both recorded
- numeric metric deltas are computed as `candidate - baseline`
- run summary records `baseline_case_count`

- [ ] **Step 3: Add write-verify runner measurement test**

Extend `tests/unit/v4/test_evaluation_runners.py` to assert write-verify runner metrics include:

- `verification_duration_ms`
- `verification_output_chars`
- `verification_output_token_estimate`

- [ ] **Step 4: Implement minimal measurement support**

Modify:

- `src/homllm_v4/contracts/evaluation.py`
- `src/homllm_v4/evaluation/harness.py`
- `src/homllm_v4/evaluation/runners.py`

Implementation constraints:

- do not introduce LLM judging
- do not introduce baseline execution outside named runner hooks
- do not change existing runtime loop behavior

- [ ] **Step 5: Run measurement tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_evaluation_harness.py tests\unit\v4\test_evaluation_runners.py tests\unit\v4\test_patch_case_evaluation.py -q
```

Expected: pass.

## Task 7: Runnable Fixture Suite Entrypoint

- [ ] **Step 1: Add API test for fixture suite runner**

Create `tests/unit/v4/test_fixture_suite_runner.py` to assert `run_python_patch_fixture_suite(...)`:

- runs four deterministic cases
- returns `passed_cases == 4`
- persists `evaluation/summary.json`
- includes run-level summary metrics

- [ ] **Step 2: Add CLI parser test**

Extend `tests/unit/v4/test_cli_api.py` to assert `eval-fixture-patch` prints JSON with:

- `run_id`
- `total_cases`
- `passed_cases`
- `failed_cases`
- `artifact_root`
- `summary_metrics`

- [ ] **Step 3: Implement fixture suite runner and CLI command**

Create:

- `src/homllm_v4/evaluation/fixture_suites.py`

Modify:

- `src/homllm_v4/api.py`
- `src/homllm_v4/cli.py`
- `src/homllm_v4/evaluation/__init__.py`

- [ ] **Step 4: Run CLI smoke**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-fixture-patch --fixture-root fixtures\v4\python_patch_repo --workspace-root temp\v4_fixture_patch_work --artifact-root temp\v4_fixture_patch_runs --run-id fixture-cli-smoke
```

Expected: exit `0`, `passed_cases == 4`, `failed_cases == 0`.

## Explicit Exclusions

- No LLM patch generation.
- No SWE-bench integration.
- No Terminal-bench integration.
- No broad refactor support.
- No rollback implementation.
- No product UI.

## Self-Review

- Spec coverage: covers the recommended M5 first task class from the M1-M4 audit: small verified Python patch tasks against a frozen fixture repository.
- Placeholder scan: no TBD/TODO/implement-later placeholders.
- Type consistency: uses existing `EvaluationCase`, `WriteVerifyLoopRequest`, `PatchApplyRequest`, `CommandRunRequest`, and `make_write_verify_runner` contracts.
