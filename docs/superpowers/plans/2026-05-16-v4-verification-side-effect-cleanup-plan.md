# V4 Verification Side-Effect Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `rollback_on_failure=True`, clean up arbitrary verification side effects after they are detected by restoring modified/deleted files and deleting newly created files outside the patch set.

**Architecture:** Reuse the workspace snapshot already taken before verification. Change snapshot values from hashes to file bytes so rollback can restore content. Side-effect cleanup is only attempted for `verification_side_effect` stops and only when rollback is enabled; patch rollback remains owned by `WorkspacePatchService`.

**Tech Stack:** Python, pytest, HOM-LLM v4 `WriteVerifyLoop`.

---

### Task 1: Add Failing Cleanup Tests

**Files:**
- Modify: `tests/unit/v4/test_write_verify_loop.py`

- [ ] **Step 1: Add created-file cleanup test**

Add:

```python
def test_write_verify_loop_cleans_created_side_effect_when_rollback_enabled(
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

    result = loop(tmp_path).run(request(tmp_path, patch, (command,), rollback_on_failure=True))

    assert result.stop_reason == "verification_side_effect"
    assert not (tmp_path / "side_effect.txt").exists()
    assert result.error is not None
    assert result.error.details["cleaned_files"] == ("side_effect.txt",)
```

- [ ] **Step 2: Add modified-file restore test**

Add:

```python
def test_write_verify_loop_restores_modified_side_effect_when_rollback_enabled(
    tmp_path: Path,
) -> None:
    target = tmp_path / "demo.py"
    original = "VALUE = 1\n"
    target.write_text(original, encoding="utf-8")
    unrelated = tmp_path / "notes.txt"
    unrelated.write_text("before\n", encoding="utf-8")
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
            "from pathlib import Path; Path('notes.txt').write_text('after\\n'); raise SystemExit(0)",
        ),
        timeout_seconds=5,
    )

    result = loop(tmp_path).run(request(tmp_path, patch, (command,), rollback_on_failure=True))

    assert result.stop_reason == "verification_side_effect"
    assert unrelated.read_text(encoding="utf-8") == "before\n"
    assert result.error is not None
    assert result.error.details["cleaned_files"] == ("notes.txt",)
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_write_verify_loop.py::test_write_verify_loop_cleans_created_side_effect_when_rollback_enabled tests\unit\v4\test_write_verify_loop.py::test_write_verify_loop_restores_modified_side_effect_when_rollback_enabled -q
```

Expected: FAIL because side-effect files are detected but not cleaned.

### Task 2: Implement Cleanup from Snapshot

**Files:**
- Modify: `src/homllm_v4/runtime/write_verify_loop.py`

- [ ] **Step 1: Change snapshot to store bytes**

Change `_workspace_snapshot` return type and body:

```python
def _workspace_snapshot(root: Path, *, ignored_files: tuple[str, ...]) -> dict[str, bytes]:
    ...
        snapshot[relative] = path.read_bytes()
```

`_changed_files` continues to compare values.

- [ ] **Step 2: Add cleanup helper**

Add:

```python
def _cleanup_side_effects(
    root: Path,
    *,
    before: dict[str, bytes],
    changed_files: tuple[str, ...],
    enabled: bool,
) -> tuple[str, ...]:
    if not enabled:
        return ()
    cleaned: list[str] = []
    for relative in changed_files:
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            continue
        if relative in before:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(before[relative])
        elif path.exists() and path.is_file():
            path.unlink()
        cleaned.append(relative)
    return tuple(cleaned)
```

- [ ] **Step 3: Invoke cleanup on side-effect stop**

Before creating `CapabilityError`, call:

```python
                cleaned_files = _cleanup_side_effects(
                    Path(request.workspace_root),
                    before=before_verification,
                    changed_files=side_effect_files,
                    enabled=request.rollback_on_failure,
                )
```

Add to error details:

```python
details={"changed_files": side_effect_files, "cleaned_files": cleaned_files}
```

- [ ] **Step 4: Run write loop tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_write_verify_loop.py -q
```

Expected: all write loop tests pass.

### Task 3: Verify and Audit

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Run full gates**

Run v4 tests, full unit tests, compileall, and forbidden v3 import scan.

- [ ] **Step 2: Run real-index benchmark smoke**

Run full `eval-real-index-provider-patch` with fresh roots.

- [ ] **Step 3: Update audits**

Record that arbitrary verification side effects are now detected and cleaned when rollback is enabled. Keep remaining limitations: no OS-level sandbox and cleanup is best-effort within local workspace snapshots.
