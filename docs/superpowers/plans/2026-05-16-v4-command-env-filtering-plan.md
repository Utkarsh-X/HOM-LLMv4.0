# v4 Command Environment Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent v4 verification commands from inheriting arbitrary parent-process environment variables while allowing explicitly approved runtime variables.

**Architecture:** `CommandPolicy` owns the allowlist of environment variable names. `LocalCommandService` constructs a filtered `env` dictionary for every subprocess and passes it to `subprocess.run(shell=False)`, keeping command execution structured and policy-owned.

**Tech Stack:** Python dataclasses, `subprocess.run`, pytest.

---

## File Structure

- Modify: `src/homllm_v4/contracts/command.py`
  - Add a backward-compatible `allowed_env_vars` field to `CommandPolicy`.
- Modify: `src/homllm_v4/services/command_service.py`
  - Build filtered subprocess environment from `CommandPolicy.allowed_env_vars`.
  - Pass filtered environment to `subprocess.run`.
- Modify: `tests/unit/v4/test_command_service.py`
  - Add red-green tests for default secret filtering and explicit environment allowlisting.
- Modify after verification: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - Record the command environment filtering capability and fresh verification evidence.
- Modify after verification: `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Record the safety improvement and remaining sandbox gaps.

---

### Task 1: Red Tests For Environment Filtering

**Files:**
- Modify: `tests/unit/v4/test_command_service.py`

- [ ] **Step 1: Add tests that define the desired subprocess environment behavior**

Add two tests:

```python
def test_command_service_filters_unlisted_environment_variables(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HOMLLM_SHOULD_NOT_LEAK", "secret")
    service = LocalCommandService(
        policy=CommandPolicy(
            allowed_executables=(Path(sys.executable).name,),
            default_timeout_seconds=5,
            max_timeout_seconds=10,
        )
    )

    result = service.run(
        CommandRunRequest(
            task_id="task-env-filter",
            workspace_root=str(tmp_path),
            cwd=".",
            argv=(
                sys.executable,
                "-c",
                "import os; raise SystemExit(1 if os.environ.get('HOMLLM_SHOULD_NOT_LEAK') else 0)",
            ),
            timeout_seconds=5,
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.exit_code == 0


def test_command_service_allows_explicit_environment_variables(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HOMLLM_ALLOWED_ENV", "visible")
    service = LocalCommandService(
        policy=CommandPolicy(
            allowed_executables=(Path(sys.executable).name,),
            default_timeout_seconds=5,
            max_timeout_seconds=10,
            allowed_env_vars=("HOMLLM_ALLOWED_ENV",),
        )
    )

    result = service.run(
        CommandRunRequest(
            task_id="task-env-allow",
            workspace_root=str(tmp_path),
            cwd=".",
            argv=(
                sys.executable,
                "-c",
                "import os; raise SystemExit(0 if os.environ.get('HOMLLM_ALLOWED_ENV') == 'visible' else 1)",
            ),
            timeout_seconds=5,
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.exit_code == 0
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_command_service.py -q
```

Expected:
- `test_command_service_filters_unlisted_environment_variables` fails because the secret env var is inherited.
- `test_command_service_allows_explicit_environment_variables` may error until `allowed_env_vars` exists.

---

### Task 2: Implement Minimal Environment Filtering

**Files:**
- Modify: `src/homllm_v4/contracts/command.py`
- Modify: `src/homllm_v4/services/command_service.py`

- [ ] **Step 1: Add policy field**

Add a backward-compatible field:

```python
allowed_env_vars: tuple[str, ...] = (
    "PATH",
    "PATHEXT",
    "SystemRoot",
    "COMSPEC",
    "TEMP",
    "TMP",
    "PYTHONPATH",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
)
```

- [ ] **Step 2: Filter subprocess environment**

In `LocalCommandService`, import `os`, add:

```python
def _environment(self) -> dict[str, str]:
    return {
        name: os.environ[name]
        for name in self.policy.allowed_env_vars
        if name in os.environ
    }
```

Pass it to `subprocess.run`:

```python
env=self._environment(),
```

- [ ] **Step 3: Run targeted tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_command_service.py -q
```

Expected: all command service tests pass.

---

### Task 3: Full Verification And Audit Update

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Run v4 tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
```

Expected: v4 tests pass.

- [ ] **Step 2: Run full unit suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
```

Expected: unit suite passes.

- [ ] **Step 3: Run compile verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
```

Expected: exit code `0`.

- [ ] **Step 4: Run import boundary scan**

Run:

```powershell
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected: no output.

- [ ] **Step 5: Run real-index provider patch benchmark**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_env_filter --artifact-root temp\v4_real_index_provider_patch_runs_env_filter --run-id real-index-provider-patch-env-filter-check --smoke-safe
```

Expected:
- `failed_cases=0`
- `passed_cases=9`
- `stop_reason_counts` contains only `verified`.

- [ ] **Step 6: Update audits**

Record:
- command execution now filters subprocess environment variables by policy;
- this is not a substitute for OS-level sandboxing;
- fresh verification command outputs.

---

## Self-Review

Spec coverage:
- The plan covers environment leakage from command execution.
- It preserves existing structured argv/cwd/timeout/approval behavior.
- It does not attempt OS-level sandboxing or network isolation.

Placeholder scan:
- No placeholders or deferred implementation steps are present.

Type consistency:
- `CommandPolicy.allowed_env_vars` is used by `LocalCommandService._environment`.
- Tests use existing `CommandPolicy`, `CommandRunRequest`, and `LocalCommandService` names.
