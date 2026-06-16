# v4 Provider Prompt Limit CLI Propagation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the provider prompt-size gate through the real-index provider patch CLI and v3-backed planner factory so live-provider runs can cap prompt size before spending tokens.

**Architecture:** Keep `ProviderBackedEditProposer` as the enforcement point. Thread an optional `max_prompt_chars` policy from CLI to `run_real_index_provider_patch_suite`, then through `_build_planner` into `build_v3_provider_proposed_patch_planner`, which constructs `ProviderBackedEditProposer(max_prompt_chars=...)`.

**Tech Stack:** Python argparse, pytest, existing v4 provider planner factory.

---

## File Structure

- Modify: `src/homllm_v4/cli.py`
  - Add `--max-prompt-chars` to `eval-real-index-provider-patch`.
  - Pass it into `run_real_index_provider_patch_suite`.
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
  - Add `max_prompt_chars` parameter.
  - Pass it into `_build_planner` only when the injected builder accepts it.
- Modify: `src/homllm_v4/adapters/v3_provider_patch_factory.py`
  - Add `max_prompt_chars` parameter.
  - Pass it into `ProviderBackedEditProposer`.
- Modify: `tests/unit/v4/test_provider_fixture_cli.py`
  - Assert CLI passes `max_prompt_chars` to the suite.
- Modify: `tests/unit/v4/test_v3_provider_patch_factory.py`
  - Assert factory enforces the prompt cap and does not call the provider when the prompt is oversized.
- Modify after verification: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - Record CLI/factory prompt cap exposure.
- Modify after verification: `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Record this as live-run cost safety.

---

### Task 1: Red Tests For Propagation

**Files:**
- Modify: `tests/unit/v4/test_provider_fixture_cli.py`
- Modify: `tests/unit/v4/test_v3_provider_patch_factory.py`

- [ ] **Step 1: Add CLI propagation assertion**

In `test_cli_runs_real_index_provider_patch_suite`, add the CLI flag:

```python
"--max-prompt-chars",
"12345",
```

Then assert:

```python
assert captured["max_prompt_chars"] == 12345
```

- [ ] **Step 2: Add factory enforcement test**

Add a provider that records calls:

```python
class RecordingProvider(FakeProvider):
    def __init__(self) -> None:
        self.called = False

    def propose_edit(self, request: ProviderEditProposalRequest) -> ProviderEditProposalResponse:
        self.called = True
        return super().propose_edit(request)
```

Add test:

```python
def test_v3_provider_patch_factory_applies_provider_prompt_limit(tmp_path: Path) -> None:
    original = "def add(a, b):\n    return a - b\n"
    (tmp_path / "calculator.py").write_text(original, encoding="utf-8")
    provider = RecordingProvider()

    planner = build_v3_provider_proposed_patch_planner(
        config_path=Path("config.yaml"),
        workspace_root=tmp_path,
        edit_provider=provider,
        component_builder=fake_component_builder,
        max_prompt_chars=10,
    )

    result = planner.plan(
        ProviderProposedPatchPlanRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            query="fix add",
            task_class="python_patch",
            index_id="idx",
            target_file="calculator.py",
            intent="fix add",
            expected_behavior="add returns a sum",
            verification_argv=(sys.executable, "-m", "pytest", ".", "-q"),
            retrieval_policy={"intent": "EXPLAIN", "top_k": 5},
            expected_content_hash=content_hash(original),
        )
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "provider_prompt_budget_exceeded"
    assert provider.called is False
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_runs_real_index_provider_patch_suite tests\unit\v4\test_v3_provider_patch_factory.py -q
```

Expected:
- CLI test fails because `--max-prompt-chars` is unknown.
- Factory test fails because `max_prompt_chars` is not accepted.

---

### Task 2: Wire Prompt Limit Through Boundaries

**Files:**
- Modify: `src/homllm_v4/cli.py`
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
- Modify: `src/homllm_v4/adapters/v3_provider_patch_factory.py`

- [ ] **Step 1: Add CLI argument**

Add:

```python
real_index_provider_patch.add_argument("--max-prompt-chars", type=int)
```

Pass:

```python
max_prompt_chars=args.max_prompt_chars,
```

- [ ] **Step 2: Add suite parameter**

Add to `run_real_index_provider_patch_suite`:

```python
max_prompt_chars: int | None = None,
```

Pass into `_build_planner`.

- [ ] **Step 3: Pass into builder only when supported**

In `_build_planner`, include `max_prompt_chars=max_prompt_chars` only if `_accepts_keyword(planner_builder, "max_prompt_chars")`.

- [ ] **Step 4: Add factory parameter**

Add to `build_v3_provider_proposed_patch_planner`:

```python
max_prompt_chars: int | None = None,
```

Pass into `ProviderBackedEditProposer`.

- [ ] **Step 5: Run targeted tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_runs_real_index_provider_patch_suite tests\unit\v4\test_v3_provider_patch_factory.py -q
```

Expected: tests pass.

---

### Task 3: Full Verification And Audit Update

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Run focused provider/CLI tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py tests\unit\v4\test_v3_provider_patch_factory.py tests\unit\v4\test_provider_edit_proposer.py -q
```

Expected: pass.

- [ ] **Step 2: Run v4 and full unit suites**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
```

Expected: pass.

- [ ] **Step 3: Run compile and boundary checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected: compile exits `0`; boundary scan has no output.

- [ ] **Step 4: Run real-index CLI benchmark compatibility check**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_prompt_limit_cli --artifact-root temp\v4_real_index_provider_patch_runs_prompt_limit_cli --run-id real-index-provider-patch-prompt-limit-cli-check --smoke-safe
```

Expected:
- `passed_cases=13`
- `failed_cases=0`
- `baseline_case_count=10`
- `stop_reason_counts={"verified":13}`

- [ ] **Step 5: Update audits**

Record:
- `--max-prompt-chars` exists for real-index provider patch CLI;
- v3 provider patch factory applies the cap before provider invocation;
- default benchmark remains compatible when no cap is set.

---

## Self-Review

Spec coverage:
- This exposes the already-implemented cost/safety policy at the live-run CLI/factory boundary.
- It does not change retrieval, patching, verification, or default benchmark behavior.

Placeholder scan:
- No placeholders or deferred implementation steps are present.

Type consistency:
- `max_prompt_chars` flows from CLI to suite to planner builder to `ProviderBackedEditProposer`.
