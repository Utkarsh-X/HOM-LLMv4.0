# V4 Real-Index Provider Planner Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable v3-backed provider-proposed patch planner factory and an opt-in smoke proving real v3 indexed retrieval can feed provider-proposed patch planning.

**Architecture:** v3 imports stay under `src/homllm_v4/adapters/`. The factory composes existing v3 read-only components, `DirectReadService`, and `ProviderBackedEditProposer` into `ProviderProposedPatchPlanner`. The smoke uses fake provider output, not live LLM output.

**Tech Stack:** Python, pytest, existing v4 provider planner, existing v3 read-only component factory.

---

## File Structure

- Create `src/homllm_v4/adapters/v3_provider_patch_factory.py`
  - Defines `build_v3_provider_proposed_patch_planner`.
- Modify `src/homllm_v4/adapters/__init__.py`
  - Export the new factory.
- Create `tests/unit/v4/test_v3_provider_patch_factory.py`
  - Unit test with fake v3 read-only components.
- Modify `tests/unit/v4/test_v3_read_only_factory.py`
  - Add opt-in real-index smoke using `HOMLLM_V4_RUN_REAL_V3_SMOKE=1`.
- Modify architecture audits.

## Task 1: Failing Factory Test

**Files:**
- Create: `tests/unit/v4/test_v3_provider_patch_factory.py`

- [ ] **Step 1: Add failing test**

Test should:

- monkeypatch/fake `build_v3_read_only_components`
- pass a fake provider to `build_v3_provider_proposed_patch_planner`
- assert returned object is `ProviderProposedPatchPlanner`
- assert planning against a temp workspace succeeds with fake retrieval/provider

- [ ] **Step 2: Run test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_provider_patch_factory.py::test_v3_provider_patch_factory_builds_provider_proposed_planner -q
```

Expected: FAIL because `v3_provider_patch_factory` does not exist.

## Task 2: Factory Implementation

**Files:**
- Create: `src/homllm_v4/adapters/v3_provider_patch_factory.py`
- Modify: `src/homllm_v4/adapters/__init__.py`

- [ ] **Step 1: Implement factory**

Signature:

```python
def build_v3_provider_proposed_patch_planner(
    *,
    config_path: Path,
    workspace_root: Path,
    edit_provider: EditProposalProvider,
    smoke_safe: bool = True,
    component_builder=build_v3_read_only_components,
) -> ProviderProposedPatchPlanner:
```

It should:

- build v3 read-only components
- get `evidence.retrieve` service
- create `DirectReadService(workspace_root=workspace_root)`
- create `ProviderBackedEditProposer(provider=edit_provider)`
- return `ProviderProposedPatchPlanner`

## Task 3: Opt-In Real-Index Smoke

**Files:**
- Modify: `tests/unit/v4/test_v3_read_only_factory.py`

- [ ] **Step 1: Add fake prompt-aware provider**

Provider should parse the `Evidence IDs:` line from prompt and return JSON with:

- target file `api/routes.py`
- new content equal to current file content
- evidence ids from prompt

- [ ] **Step 2: Add skipped-by-default smoke**

Skip unless `HOMLLM_V4_RUN_REAL_V3_SMOKE=1`.

Use:

- workspace `test_repo`
- target `api/routes.py`
- query `admin_search_endpoint in api routes`
- fake provider
- `ProviderProposedPatchPlanner.plan(...)`

Assert:

- result ok
- patch target is `api/routes.py`
- patch new content equals original content
- patch plan has evidence ids

## Task 4: Verification

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_provider_patch_factory.py -q
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
$env:HOMLLM_V4_RUN_REAL_V3_SMOKE='1'; .\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_provider_proposed_patch_planner_smoke -q -s
```

Expected:

- factory unit tests pass.
- v4/full suites pass.
- compileall passes.
- boundary scan returns no matches.
- opt-in real-index provider planner smoke passes when local indexes are available.

## Self-Review

- Spec coverage: This proves real indexed retrieval can feed provider-proposed patch planning. It does not call a live provider and does not apply patches.
- Placeholder scan: No TBD/TODO placeholders are present.
- Type consistency: factory names match existing v3 adapter factory naming.
