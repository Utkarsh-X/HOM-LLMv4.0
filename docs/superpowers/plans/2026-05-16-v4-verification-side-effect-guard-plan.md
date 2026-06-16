# V4 Verification Side-Effect Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect when verification commands mutate workspace files outside the patch-service-managed file set, preventing silent success after unintended side effects.

**Architecture:** `WriteVerifyLoop` will snapshot the workspace after patch application and before verification, then compare after verification. Files changed by the patch itself are allowed; runtime/cache artifacts such as `.homllm/`, `__pycache__/`, `.pytest_cache/`, and `.pyc` files are ignored. Unexpected created/modified/deleted files return a structured `verification_side_effect` stop reason and error.

**Tech Stack:** Python, pytest, HOM-LLM v4 write-verify runtime, existing `CapabilityError`.

---

### Task 1: Add Failing Side-Effect Test

**Files:**
- Modify: `tests/unit/v4/test_write_verify_loop.py`

- [ ] **Step 1: Add a verification side-effect test**

Add:

```python
def test_write_verify_loop_blocks_unexpected_verification_file_side_effect(
    tmp_path: Path,
) -> None:
    target = tmp_path / "demo.py"
    original = "VALUE = 1\n"
    target.write_text(original, encoding="utf-8")
    patch = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash(original), "VALUE = 2\n"),),
    )
    command = CommandRunRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        cwd=".",
        argv=(
            sys.executable,
            "-c",
            "from pathlib import Path; Path('side_effect.txt').write_text('bad'); raise SystemExit(0)",
        ),
        timeout_seconds=5,
    )

    result = loop(tmp_path).run(request(tmp_path, patch, (command,)))

    assert result.stop_reason == "verification_side_effect"
    assert result.error is not None
    assert result.error.code == "verification_side_effect"
    assert result.error.details["changed_files"] == ("side_effect.txt",)
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_write_verify_loop.py::test_write_verify_loop_blocks_unexpected_verification_file_side_effect -q
```

Expected: FAIL because the loop currently returns `verified`.

### Task 2: Implement Workspace Snapshot Side-Effect Detection

**Files:**
- Modify: `src/homllm_v4/contracts/write_loop.py`
- Modify: `src/homllm_v4/runtime/write_verify_loop.py`

- [ ] **Step 1: Add stop reason**

Add `"verification_side_effect"` to `WriteVerifyStopReason`.

- [ ] **Step 2: Import hashing and Path**

In `write_verify_loop.py`, add:

```python
import hashlib
from pathlib import Path
```

- [ ] **Step 3: Snapshot before verification**

Before `_run_verification(request)`, compute:

```python
            allowed_side_effect_files = _patch_files(patch_result)
            before_verification = _workspace_snapshot(
                Path(request.workspace_root),
                ignored_files=allowed_side_effect_files,
            )
```

- [ ] **Step 4: Compare after verification**

After `_run_verification`, compute:

```python
            side_effect_files = _changed_files(
                before_verification,
                _workspace_snapshot(
                    Path(request.workspace_root),
                    ignored_files=allowed_side_effect_files,
                ),
            )
            if side_effect_files:
                rollback_result = self._rollback_if_enabled(request, patch_result)
                return self._result(
                    request,
                    "verification_side_effect",
                    patch_result,
                    verification_results,
                    CapabilityError(
                        code="verification_side_effect",
                        message="verification command changed files outside the patch set",
                        recoverable=True,
                        retryable=False,
                        details={"changed_files": side_effect_files},
                    ),
                    patch_attempt_count=attempt_index,
                    rollback_result=rollback_result,
                )
```

- [ ] **Step 5: Add helpers**

Add module helpers:

```python
def _patch_files(patch_result: PatchApplyResult | None) -> tuple[str, ...]:
    if patch_result is None:
        return ()
    return tuple(file_result.file_path for file_result in patch_result.file_results)


def _workspace_snapshot(root: Path, *, ignored_files: tuple[str, ...]) -> dict[str, str]:
    ignored = {Path(file_path).as_posix() for file_path in ignored_files}
    snapshot: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in ignored or _ignored_snapshot_path(relative):
            continue
        snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def _changed_files(before: dict[str, str], after: dict[str, str]) -> tuple[str, ...]:
    files = set(before) | set(after)
    return tuple(sorted(file_path for file_path in files if before.get(file_path) != after.get(file_path)))


def _ignored_snapshot_path(relative_path: str) -> bool:
    parts = set(Path(relative_path).parts)
    if parts & {".git", ".homllm", "__pycache__", ".pytest_cache"}:
        return True
    return relative_path.endswith((".pyc", ".pyo"))
```

- [ ] **Step 6: Run write loop tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_write_verify_loop.py -q
```

Expected: all write loop tests pass.

### Task 3: Verify and Audit

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Run v4 and full unit gates**

Run v4 tests, full unit tests, compileall, and forbidden v3 import scan.

- [ ] **Step 2: Run real-index benchmark smoke**

Run `eval-real-index-provider-patch` with fresh roots to ensure compile/import cache artifacts are ignored and benchmark still passes.

- [ ] **Step 3: Update audits**

Record that verification side effects are now detected and blocked, while arbitrary side-effect rollback remains incomplete.
