# v4 Real-Index Provider Execution Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in smoke test proving real v3 indexed retrieval can feed a fake-provider proposal into the v4 patch and verification runtime without mutating the real repository fixture.

**Architecture:** The test must copy `test_repo` into a temporary workspace, build a `ProviderProposedPatchPlanner` with real v3 retrieval and a fake prompt-aware provider, generate a no-op patch request, then execute that request through `WriteVerifyLoop`. The runtime stays bounded by `WorkspacePatchService`, `LocalCommandService`, typed requests, and artifact/event persistence.

**Tech Stack:** Python, pytest, v4 contracts/services, v3 adapter factory, local `compileall` verification.

---

## File Structure

- Modify: `tests/unit/v4/test_v3_read_only_factory.py`
  - Add an opt-in real-index provider-proposed patch execution smoke beside the existing real-index planning smoke.
  - Reuse `PromptAwareNoopProvider` so the provider does not call a live model.
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - Record the new smoke command and remaining limitation.
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Update the prompt-to-artifact checklist and fresh verification evidence.

No production file should change unless the failing test exposes a real integration defect.

---

### Task 1: Add the Failing Smoke Test

**Files:**
- Modify: `tests/unit/v4/test_v3_read_only_factory.py`

- [ ] **Step 1: Add imports required by the smoke**

Add these imports near the top of the file:

```python
import hashlib
import shutil
import sys
```

Add these v4 imports:

```python
from homllm_v4.contracts.command import CommandPolicy, CommandRunRequest
from homllm_v4.contracts.write_loop import WriteVerifyLoopRequest
from homllm_v4.runtime.write_verify_loop import WriteVerifyLoop
from homllm_v4.services.command_service import LocalCommandService
from homllm_v4.services.patch_service import WorkspacePatchService
```

- [ ] **Step 2: Add a local content hash helper**

Add this helper near `clear_recorders()`:

```python
def normalized_content_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()
```

- [ ] **Step 3: Add the opt-in smoke test**

Add this test after `test_real_v3_provider_proposed_patch_planner_smoke`:

```python
@pytest.mark.skipif(
    os.environ.get("HOMLLM_V4_RUN_REAL_V3_SMOKE") != "1",
    reason="real v3 smoke is opt-in because it can touch local indexes and model runtimes",
)
def test_real_v3_provider_proposed_patch_execution_smoke(tmp_path: Path) -> None:
    repo_root = Path.cwd()
    source_workspace = repo_root / "test_repo"
    workspace_root = tmp_path / "workspace"
    shutil.copytree(source_workspace, workspace_root)
    target_file = "api/routes.py"
    original = (workspace_root / target_file).read_text(encoding="utf-8")
    planner = build_v3_provider_proposed_patch_planner(
        config_path=Path("configs/agentic/ccg_stage2_canary_v1/ccg_stage2_agentic_ro3.yaml"),
        workspace_root=workspace_root,
        edit_provider=PromptAwareNoopProvider(
            target_file=target_file,
            new_content=original,
        ),
        smoke_safe=True,
    )

    plan_result = planner.plan(
        ProviderProposedPatchPlanRequest(
            task_id="real-provider-proposed-exec",
            workspace_root=str(workspace_root),
            query="admin_search_endpoint in api routes",
            task_class="python_patch",
            index_id="idx",
            target_file=target_file,
            intent="execute a provider-proposed no-op edit to admin search endpoint safely",
            expected_behavior="real indexed retrieval feeds provider patch execution and verification",
            verification_argv=(sys.executable, "-m", "compileall", "-q", "api/routes.py"),
            retrieval_policy={"intent": "EXPLAIN", "top_k": 20},
            expected_content_hash=normalized_content_hash(original),
        )
    )
    assert plan_result.ok is True
    assert plan_result.output is not None

    manager = ArtifactManager(
        workspace_root=workspace_root,
        artifact_root=tmp_path / ".homllm" / "runs",
    )
    manager.create_run("real-provider-exec-smoke", {})
    loop = WriteVerifyLoop(
        patch_service=WorkspacePatchService(),
        command_service=LocalCommandService(
            policy=CommandPolicy(
                allowed_executables=(Path(sys.executable).name,),
                default_timeout_seconds=10,
                max_timeout_seconds=10,
            )
        ),
        artifact_manager=manager,
        event_writer=EventWriter(
            tmp_path / ".homllm" / "runs" / "real-provider-exec-smoke" / "events.jsonl"
        ),
    )

    result = loop.run(
        WriteVerifyLoopRequest(
            task_id="real-provider-proposed-exec",
            run_id="real-provider-exec-smoke",
            workspace_root=str(workspace_root),
            patch_request=plan_result.output.patch_request,
            verification_commands=(
                CommandRunRequest(
                    task_id="real-provider-proposed-exec",
                    workspace_root=str(workspace_root),
                    cwd=".",
                    argv=(sys.executable, "-m", "compileall", "-q", "api/routes.py"),
                    timeout_seconds=10,
                ),
            ),
            max_verification_commands=1,
            max_patch_attempts=1,
            rollback_on_failure=True,
        )
    )

    assert result.stop_reason == "verified"
    assert result.patch_attempt_count == 1
    assert result.patch_result is not None
    assert result.patch_result.applied is True
    assert len(result.verification_results) == 1
    assert result.verification_results[0].exit_code == 0
    assert (workspace_root / target_file).read_text(encoding="utf-8") == original
    assert (source_workspace / target_file).read_text(encoding="utf-8") == original
```

- [ ] **Step 4: Run the new test to verify RED**

Run:

```powershell
$env:HOMLLM_V4_RUN_REAL_V3_SMOKE='1'; .\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_provider_proposed_patch_execution_smoke -q -s
```

Expected:

- If required imports/helpers are not added yet, it fails with an import/name error.
- If existing production code already satisfies the behavior after adding the test scaffolding, record that no production implementation was required.

---

### Task 2: Implement Minimal Required Changes

**Files:**
- Modify only if the RED test exposes a real defect:
  - `src/homllm_v4/adapters/v3_provider_patch_factory.py`
  - `src/homllm_v4/planning/provider_patch_planner.py`
  - `src/homllm_v4/runtime/write_verify_loop.py`
  - `src/homllm_v4/services/patch_service.py`
  - `src/homllm_v4/services/command_service.py`

- [ ] **Step 1: Keep production unchanged if the test passes**

If the smoke passes after test scaffolding, do not invent production changes.

- [ ] **Step 2: If production fails, fix only the proven integration defect**

Acceptable fix categories:

```text
- adapter path/config translation defect
- direct-read workspace-root defect
- patch request hash/freshness defect
- command allowlist/cwd defect
- artifact path defect
```

Do not add:

```text
- live provider calls
- autonomous file selection
- broad benchmark harness changes
- new planner abstractions
```

- [ ] **Step 3: Re-run targeted test**

Run:

```powershell
$env:HOMLLM_V4_RUN_REAL_V3_SMOKE='1'; .\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_provider_proposed_patch_execution_smoke -q -s
```

Expected: `1 passed`.

---

### Task 3: Verification Gate

**Files:**
- No new files expected.

- [ ] **Step 1: Run the full opt-in real v3 smoke group**

Run:

```powershell
$env:HOMLLM_V4_RUN_REAL_V3_SMOKE='1'; .\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_read_only_loop_smoke tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_retrieval_backed_patch_planner_smoke tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_provider_proposed_patch_planner_smoke tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_provider_proposed_patch_execution_smoke -q -s
```

Expected: `4 passed`.

- [ ] **Step 2: Run v4 unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
```

Expected: all pass, with real smoke skipped by default.

- [ ] **Step 3: Run full unit suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
```

Expected: all pass, with real smoke skipped by default.

- [ ] **Step 4: Run compile check**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
```

Expected: exit code `0`.

- [ ] **Step 5: Run non-adapter v3 import boundary scan**

Run:

```powershell
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected: no output.

- [ ] **Step 6: Run provider fixture CLI smoke**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-fixture-provider-patch --fixture-root fixtures\v4\python_patch_repo --workspace-root temp\v4_fixture_provider_patch_work_real_index --artifact-root temp\v4_fixture_provider_patch_runs_real_index --run-id provider-fixture-real-index-check
```

Expected: `failed_cases` is `0`.

If this exact workspace/run id has already been used, choose fresh names. The fixture runner intentionally refuses to overwrite existing case workspaces.

---

### Task 4: Update Audits

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Record the new smoke evidence**

Add the opt-in command and result to both audit files.

- [ ] **Step 2: Update remaining weakness language**

Change the previous weakness from:

```text
provider-proposed patch execution is still deterministic fixture-only
```

to:

```text
provider-proposed patch execution now has an opt-in real-index smoke with a fake no-op provider, but still lacks live provider synthesis and a real multi-case indexed write benchmark.
```

- [ ] **Step 3: Do not mark active goal complete**

The remaining product-grade gaps still include:

```text
- no live LLM patch synthesis result
- no autonomous target-file selection
- no real multi-case indexed-repo write benchmark
- no baseline write comparison
- no OS-level sandbox backend
- no product-facing session/approval UX
```

---

## Self-Review

Spec coverage:

- The plan covers the exact remaining gap: real-index provider-proposed patch execution through v4 patch and verification runtime.
- It avoids mutation of `test_repo` by using `shutil.copytree`.
- It keeps model calls fake-provider-only and opt-in.
- It preserves v3 import boundaries by using existing adapter factories.

Placeholder scan:

- No placeholder task remains. Every command and file path is concrete.

Type consistency:

- `ProviderProposedPatchPlanRequest`, `WriteVerifyLoopRequest`, `CommandRunRequest`, and service constructors match the current v4 APIs.
