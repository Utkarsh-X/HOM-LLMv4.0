# V4 Provider-Proposed Patch Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a narrow bridge that turns retrieval evidence and a fresh direct read into a provider-proposed edit, then into an evidence-backed patch plan.

**Architecture:** The runtime still fixes target file, allowed scope, evidence set, direct read, and verification command. The provider only proposes `new_content` through `ProviderBackedEditProposer`; `EvidenceBackedPatchPlanner` remains the component that creates patch and verification requests.

**Tech Stack:** Python dataclasses, existing v4 retrieval/direct-read services, existing provider proposer, existing evidence patch planner, pytest.

---

## File Structure

- Create `src/homllm_v4/planning/provider_patch_planner.py`
  - Defines `ProviderProposedPatchPlanRequest` and `ProviderProposedPatchPlanner`.
- Modify `src/homllm_v4/planning/__init__.py`
  - Exports the new request and planner.
- Create `tests/unit/v4/test_provider_patch_planner.py`
  - Tests success path and provider evidence-scope failure using fake retrieval, direct read, and provider.
- Modify `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - Records evidence-to-provider-to-patch planning bridge.
- Modify `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Updates completed and remaining goal items.

## Task 1: Planner Tests

**Files:**
- Create: `tests/unit/v4/test_provider_patch_planner.py`

- [ ] **Step 1: Write failing success-path test**

The test should create:

- a fake retrieval service returning one `EvidenceCandidate` for `calculator.py`
- a real `DirectReadService` over `tmp_path`
- a fake provider returning valid edit JSON
- a `ProviderProposedPatchPlanner`

Expected assertions:

- result is ok
- patch target is `calculator.py`
- patch content contains `return a + b`
- patch plan evidence ids include `cand-1`
- verification command is preserved

- [ ] **Step 2: Run the success test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_patch_planner.py::test_provider_proposed_patch_planner_creates_patch_plan_from_retrieval_and_provider -q
```

Expected: FAIL because `homllm_v4.planning.provider_patch_planner` does not exist.

- [ ] **Step 3: Write failing evidence-scope rejection test**

Fake provider returns `evidence_ids=["unknown"]`.

Expected:

- result is not ok
- error code is `proposal_evidence_scope_denied`

## Task 2: Planner Implementation

**Files:**
- Create: `src/homllm_v4/planning/provider_patch_planner.py`
- Modify: `src/homllm_v4/planning/__init__.py`

- [ ] **Step 1: Implement request contract**

```python
@dataclass(frozen=True)
class ProviderProposedPatchPlanRequest:
    task_id: str
    workspace_root: str
    query: str
    task_class: str
    index_id: str
    target_file: str
    intent: str
    expected_behavior: str
    verification_argv: tuple[str, ...]
    retrieval_policy: dict[str, object]
    expected_content_hash: str | None = None
```

- [ ] **Step 2: Implement planner flow**

Flow:

1. Retrieve evidence with target file fixed.
2. Direct-read the target file with `require_hash=True`.
3. Build `EditProposalRequest` from runtime-fixed context.
4. Call `ProviderBackedEditProposer`.
5. Convert proposal to `EvidenceBackedPatchPlanRequest`.
6. Call `EvidenceBackedPatchPlanner`.

Do not apply patches or execute commands in this planner.

- [ ] **Step 3: Export planner**

Export `ProviderProposedPatchPlanRequest` and `ProviderProposedPatchPlanner` from `src/homllm_v4/planning/__init__.py`.

- [ ] **Step 4: Run targeted planner tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_patch_planner.py -q
```

Expected: all planner tests pass.

## Task 3: Documentation and Verification

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Update docs**

Record:

```text
ProviderProposedPatchPlanner connects retrieval, direct read, provider proposal, and evidence-backed patch planning without applying patches or running commands.
```

Keep limitation:

```text
No live provider evaluation or broad write benchmark is populated yet.
```

- [ ] **Step 2: Run verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected:

- v4 tests pass.
- full unit suite passes.
- compileall passes.
- boundary scan returns no matches.

## Self-Review

- Spec coverage: This plan connects provider proposal into patch planning but intentionally does not apply patches, execute commands, select targets autonomously, or call live LLM providers.
- Placeholder scan: No TBD/TODO placeholders are present.
- Type consistency: request/planner names are consistent across plan, tests, implementation, and exports.
