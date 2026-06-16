# V4 Opt-In Live Provider Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe scaffolding for opt-in live provider validation of the provider-backed edit proposal seam, skipped by default.

**Architecture:** The factory lives under `src/homllm_v4/adapters/` because it imports v3 provider implementations. Normal tests use injected fake provider classes; the live smoke test only runs when `HOMLLM_V4_RUN_LIVE_PROVIDER_SMOKE=1`.

**Tech Stack:** Python, pytest, existing v3 provider connectors, existing `V3ProviderEditProposalAdapter`, existing `ProviderBackedEditProposer`.

---

## File Structure

- Create `src/homllm_v4/adapters/v3_provider_factory.py`
  - Builds `V3ProviderEditProposalAdapter` from provider name, model, model config, optional API key, and injectable provider classes.
- Modify `src/homllm_v4/adapters/__init__.py`
  - Export `build_v3_provider_edit_adapter`.
- Create `tests/unit/v4/test_v3_provider_factory.py`
  - Tests factory translation with fake provider classes.
- Create `tests/unit/v4/test_live_provider_edit_smoke.py`
  - Skipped unless `HOMLLM_V4_RUN_LIVE_PROVIDER_SMOKE=1`.
- Modify architecture audits.

## Task 1: Factory Tests

**Files:**
- Create: `tests/unit/v4/test_v3_provider_factory.py`

- [ ] **Step 1: Write failing factory tests**

Tests should verify:

- `provider_name="gemini"` instantiates the injected Gemini class with API key.
- `provider_name="openai"` instantiates the injected OpenAI class with API key.
- unsupported provider returns `ValueError`.
- returned object can drive `ProviderBackedEditProposer` with fake provider JSON.

- [ ] **Step 2: Run one factory test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_provider_factory.py::test_factory_builds_gemini_provider_adapter_with_injected_provider_class -q
```

Expected: FAIL because `homllm_v4.adapters.v3_provider_factory` does not exist.

## Task 2: Factory Implementation

**Files:**
- Create: `src/homllm_v4/adapters/v3_provider_factory.py`
- Modify: `src/homllm_v4/adapters/__init__.py`

- [ ] **Step 1: Implement factory**

Signature:

```python
def build_v3_provider_edit_adapter(
    *,
    provider_name: str,
    model: str,
    model_config: ModelConfig,
    api_key: str | None = None,
    gemini_provider_cls: type[ProviderConnector] = GeminiProvider,
    openai_provider_cls: type[ProviderConnector] = OpenAIProvider,
) -> V3ProviderEditProposalAdapter:
```

Unsupported provider names should raise:

```python
ValueError(f"unsupported provider for edit proposals: {provider_name}")
```

- [ ] **Step 2: Export factory**

Update `src/homllm_v4/adapters/__init__.py`.

## Task 3: Opt-In Live Smoke Test

**Files:**
- Create: `tests/unit/v4/test_live_provider_edit_smoke.py`

- [ ] **Step 1: Add skipped-by-default smoke**

The test should:

- skip unless `HOMLLM_V4_RUN_LIVE_PROVIDER_SMOKE=1`
- read provider from `HOMLLM_V4_LIVE_PROVIDER`, default `gemini`
- read model from `HOMLLM_V4_LIVE_MODEL`, default `gemini-2.5-flash`
- build adapter with `build_v3_provider_edit_adapter`
- call `ProviderBackedEditProposer` on a tiny calculator request
- assert only that response is structurally accepted or else fail with the returned structured error

Do not run this smoke during normal verification.

## Task 4: Verification

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_provider_factory.py tests\unit\v4\test_live_provider_edit_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected:

- factory tests pass.
- live smoke is skipped by default.
- v4/full suites pass.
- compileall passes.
- boundary scan returns no matches.

## Self-Review

- Spec coverage: This plan creates safe live-provider validation scaffolding only. It does not execute live provider calls by default.
- Placeholder scan: No TBD/TODO placeholders are present.
- Type consistency: factory and adapter names match existing v4 adapter naming.
