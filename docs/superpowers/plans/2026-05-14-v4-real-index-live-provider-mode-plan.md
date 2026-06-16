# v4 Real-Index Live Provider Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in live-provider mode to the real-index provider benchmark while keeping fake-provider mode as the default.

**Architecture:** Live provider construction stays inside `src/homllm_v4/adapters/` so evaluation code does not import v3 provider internals. The benchmark gets `edit_provider_mode="fake" | "live"` and a case-id filter so live runs can be limited to one case before spending tokens broadly.

**Tech Stack:** Python, pytest, existing v3 provider adapter factory, v4 real-index benchmark CLI.

---

## File Structure

- Modify: `src/homllm_v4/adapters/v3_provider_factory.py`
  - Add `build_v3_provider_edit_adapter_from_params(...)` helper that owns `ModelConfig` construction.
- Modify: `src/homllm_v4/adapters/__init__.py`
  - Export new helper.
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
  - Add `edit_provider_mode`, live provider builder injection, live provider args, and case filtering.
- Modify: `src/homllm_v4/cli.py`
  - Add `--edit-provider-mode`, `--live-provider`, `--live-model`, `--live-api-key-env`, and `--case-id`.
- Modify tests:
  - `tests/unit/v4/test_v3_provider_factory.py`
  - `tests/unit/v4/test_real_index_provider_patch_suite.py`
  - `tests/unit/v4/test_provider_fixture_cli.py`

---

### Task 1: Add Adapter Helper Test

**Files:**
- Modify: `tests/unit/v4/test_v3_provider_factory.py`

- [ ] **Step 1: Write failing test**

Add a test importing `build_v3_provider_edit_adapter_from_params`.

The test should call:

```python
adapter = build_v3_provider_edit_adapter_from_params(
    provider_name="gemini",
    model="gemini-live-test",
    api_key="test-key",
    temperature=0.0,
    max_output_tokens=512,
    gemini_provider_cls=FakeProviderConnector,
)
```

Then call `adapter.propose_edit(...)` and assert:

```python
assert response.model == "gemini-live-test"
```

- [ ] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_provider_factory.py::test_factory_builds_provider_adapter_from_primitive_params -q
```

Expected: FAIL because helper does not exist.

---

### Task 2: Implement Adapter Helper

**Files:**
- Modify: `src/homllm_v4/adapters/v3_provider_factory.py`
- Modify: `src/homllm_v4/adapters/__init__.py`

- [ ] **Step 1: Add helper**

Implement:

```python
def build_v3_provider_edit_adapter_from_params(
    *,
    provider_name: str,
    model: str,
    api_key: str | None = None,
    temperature: float = 0.0,
    max_output_tokens: int = 2048,
    gemini_provider_cls: type[ProviderConnector] = GeminiProvider,
    openai_provider_cls: type[ProviderConnector] = OpenAIProvider,
) -> V3ProviderEditProposalAdapter:
    return build_v3_provider_edit_adapter(
        provider_name=provider_name,
        model=model,
        model_config=ModelConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ),
        api_key=api_key,
        gemini_provider_cls=gemini_provider_cls,
        openai_provider_cls=openai_provider_cls,
    )
```

- [ ] **Step 2: Export helper**

Update `__all__`.

- [ ] **Step 3: Run test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_provider_factory.py -q
```

Expected: pass.

---

### Task 3: Add Live Mode to Suite

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [ ] **Step 1: Add failing test**

Add:

```python
def test_real_index_provider_patch_suite_can_use_injected_live_provider_builder(tmp_path: Path) -> None:
    calls = []

    class RecordingProvider:
        tokens_in = 3
        tokens_out = 5
        def propose_edit(self, request):
            ...

    def build_provider(**kwargs):
        calls.append(kwargs)
        return RecordingProvider()

    result = run_real_index_provider_patch_suite(
        ...,
        run_id="live-provider-mode-suite",
        planner_builder=build_fake_planner,
        edit_provider_mode="live",
        live_provider_name="gemini",
        live_model="gemini-live-test",
        live_api_key="test-key",
        live_provider_builder=build_provider,
        case_ids=("admin-routes-noop",),
    )

    assert result.total_cases == 1
    assert result.passed_cases == 1
    assert calls[0]["provider_name"] == "gemini"
    assert calls[0]["model"] == "gemini-live-test"
    assert calls[0]["api_key"] == "test-key"
```

The `RecordingProvider` can parse the prompt target file and return no-op JSON.

- [ ] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_can_use_injected_live_provider_builder -q
```

Expected: FAIL because suite does not accept live mode params.

- [ ] **Step 3: Implement live mode**

Add parameters:

```python
edit_provider_mode: str = "fake"
live_provider_name: str = "gemini"
live_model: str = "gemini-2.5-flash"
live_api_key: str | None = None
live_provider_builder=build_v3_provider_edit_adapter_from_params
case_ids: tuple[str, ...] | None = None
```

Add `_select_cases(...)` and `_build_edit_provider(...)`.

Rules:

- `fake`: use `_PromptAwareNoopProvider` with transformed content.
- `live`: call `live_provider_builder(...)`; do not apply fake content transforms.
- unsupported mode raises `ValueError`.
- `case_ids` filters benchmark cases by id.

- [ ] **Step 4: Run suite tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: pass.

---

### Task 4: Add CLI Options

**Files:**
- Modify: `src/homllm_v4/cli.py`
- Modify: `tests/unit/v4/test_provider_fixture_cli.py`

- [ ] **Step 1: Add failing CLI test**

Extend the existing CLI test with:

```python
"--edit-provider-mode", "live",
"--live-provider", "gemini",
"--live-model", "gemini-live-test",
"--live-api-key-env", "HOMLLM_TEST_KEY",
"--case-id", "admin-routes-noop",
```

Set env var via monkeypatch:

```python
monkeypatch.setenv("HOMLLM_TEST_KEY", "test-key")
```

Assert captured kwargs include:

```python
edit_provider_mode == "live"
live_provider_name == "gemini"
live_model == "gemini-live-test"
live_api_key == "test-key"
case_ids == ("admin-routes-noop",)
```

- [ ] **Step 2: Run RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_runs_real_index_provider_patch_suite -q
```

Expected: FAIL because CLI does not accept the new options.

- [ ] **Step 3: Implement CLI args**

Add args:

```python
--edit-provider-mode choices=["fake", "live"] default="fake"
--live-provider default="gemini"
--live-model default="gemini-2.5-flash"
--live-api-key-env
--case-id action="append"
```

Resolve API key with `os.getenv(args.live_api_key_env)` when provided.

- [ ] **Step 4: Run CLI tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py -q
```

Expected: pass.

---

### Task 5: Verification and Audits

- [ ] **Step 1: Run fake default CLI benchmark**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_mode --artifact-root temp\v4_real_index_provider_patch_runs_live_mode --run-id real-index-provider-patch-live-mode-fake-check --smoke-safe
```

Expected: fake mode still passes all six cases.

- [ ] **Step 2: Run normal verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

- [ ] **Step 3: Update audits**

Record:

- live-provider mode exists for the real-index benchmark
- normal verification uses fake mode
- no live provider run result was produced unless explicitly run with credentials

---

## Self-Review

Spec coverage:

- Adds opt-in live provider execution path without network use in normal verification.
- Keeps v3 provider internals under adapters.
- Adds case filtering for cost control.

Placeholder scan:

- No placeholder tasks remain.

Type consistency:

- Uses existing provider adapter protocol and benchmark suite signatures.

