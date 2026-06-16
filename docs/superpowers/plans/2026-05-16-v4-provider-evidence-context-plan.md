# v4 Provider Evidence Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure provider-backed patch synthesis prompts include bounded evidence context, not only evidence IDs.

**Architecture:** Keep the provider seam bounded and typed. `EditProposalRequest` gains optional typed evidence context records, `ProviderProposedPatchPlanner` translates retrieved target-file candidates into those records, and `ProviderBackedEditProposer` renders them into the prompt before calling any provider.

**Tech Stack:** Python dataclasses, pytest, existing v4 planning contracts.

---

## File Structure

- Modify: `src/homllm_v4/contracts/edit_proposal.py`
  - Add `EditProposalEvidenceContext`.
  - Add `evidence_context` to `EditProposalRequest` with a backward-compatible default.
- Modify: `src/homllm_v4/planning/provider_edit_proposer.py`
  - Render evidence context in provider prompts.
- Modify: `src/homllm_v4/planning/provider_patch_planner.py`
  - Convert retrieved target-file evidence candidates into `EditProposalEvidenceContext`.
- Modify: `tests/unit/v4/test_provider_edit_proposer.py`
  - Add a prompt-rendering test for evidence context.
- Modify: `tests/unit/v4/test_provider_patch_planner.py`
  - Add a planner handoff test proving retrieved evidence content reaches the provider prompt.
- Modify after verification: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - Record evidence-context prompt support.
- Modify after verification: `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Record this as a pre-live synthesis hardening step.

---

### Task 1: Red Tests For Evidence-Informed Provider Prompts

**Files:**
- Modify: `tests/unit/v4/test_provider_edit_proposer.py`
- Modify: `tests/unit/v4/test_provider_patch_planner.py`

- [ ] **Step 1: Add prompt rendering test**

Add a test proving a manually supplied evidence context appears in the provider prompt:

```python
def test_provider_backed_edit_proposer_includes_evidence_context_in_prompt() -> None:
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use evidence.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    request = EditProposalRequest(
        task_id="task-1",
        target_file="calculator.py",
        intent="fix add",
        expected_behavior="add returns a sum",
        current_content="def add(a, b):\n    return a - b\n",
        evidence_ids=("cand-1",),
        allowed_file_paths=("calculator.py",),
        verification_summary="pytest . -q",
        evidence_context=(
            EditProposalEvidenceContext(
                evidence_id="cand-1",
                file_path="calculator.py",
                span_start=1,
                span_end=2,
                content="retrieved evidence says add currently subtracts",
            ),
        ),
    )

    result = ProviderBackedEditProposer(provider=provider).propose(request)

    assert result.ok is True
    assert provider.last_request is not None
    assert "Evidence context:" in provider.last_request.prompt
    assert "[cand-1] calculator.py:1-2" in provider.last_request.prompt
    assert "retrieved evidence says add currently subtracts" in provider.last_request.prompt
```

- [ ] **Step 2: Add planner handoff test**

Update fake retrieved evidence to include `metadata={"content": "retrieved chunk"}` and assert the provider prompt contains that retrieved chunk when planning:

```python
def test_provider_proposed_patch_planner_passes_retrieved_evidence_context_to_provider(
    tmp_path: Path,
) -> None:
    original = "def add(a, b):\n    return a - b\n"
    (tmp_path / "calculator.py").write_text(original, encoding="utf-8")
    evidence = evidence_set()
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use retrieved context.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    planner = ProviderProposedPatchPlanner(
        retrieval_service=FakeRetrievalService(output=evidence),
        direct_read_service=DirectReadService(workspace_root=tmp_path),
        edit_proposer=ProviderBackedEditProposer(provider=provider),
    )

    result = planner.plan(request(tmp_path))

    assert result.ok is True
    assert provider.last_request is not None
    assert "retrieved evidence chunk for add" in provider.last_request.prompt
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py tests\unit\v4\test_provider_patch_planner.py -q
```

Expected: failures because `EditProposalEvidenceContext` and prompt rendering do not exist yet.

---

### Task 2: Implement Typed Evidence Context

**Files:**
- Modify: `src/homllm_v4/contracts/edit_proposal.py`
- Modify: `src/homllm_v4/planning/provider_edit_proposer.py`
- Modify: `src/homllm_v4/planning/provider_patch_planner.py`

- [ ] **Step 1: Add typed contract**

Add:

```python
@dataclass(frozen=True)
class EditProposalEvidenceContext:
    evidence_id: str
    file_path: str
    span_start: int | None
    span_end: int | None
    content: str
```

Add to `EditProposalRequest`:

```python
evidence_context: tuple[EditProposalEvidenceContext, ...] = ()
```

- [ ] **Step 2: Render evidence context in prompt**

Add a helper:

```python
def _render_evidence_context(request: EditProposalRequest) -> str:
    if not request.evidence_context:
        return "Evidence context: none supplied"
    lines = ["Evidence context:"]
    for item in request.evidence_context:
        location = _format_location(item.file_path, item.span_start, item.span_end)
        lines.append(f"[{item.evidence_id}] {location}")
        lines.append(item.content)
    return "\n".join(lines)
```

Call this helper from `build_edit_proposal_prompt` before `Current content:`.

- [ ] **Step 3: Convert retrieval candidates to evidence context**

In `ProviderProposedPatchPlanner`, build context for candidates where `candidate.file_path == target_file`:

```python
EditProposalEvidenceContext(
    evidence_id=candidate.candidate_id,
    file_path=candidate.file_path,
    span_start=candidate.span_start,
    span_end=candidate.span_end,
    content=str(candidate.metadata.get("content") or ""),
)
```

Pass that tuple to `EditProposalRequest`.

- [ ] **Step 4: Run targeted tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py tests\unit\v4\test_provider_patch_planner.py -q
```

Expected: all targeted tests pass.

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
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_evidence_context --artifact-root temp\v4_real_index_provider_patch_runs_evidence_context --run-id real-index-provider-patch-evidence-context-check --smoke-safe
```

Expected:
- `failed_cases=0`
- `passed_cases=9`
- `stop_reason_counts` contains only `verified`.

- [ ] **Step 6: Update audits**

Record:
- provider prompts now include retrieved evidence context;
- live LLM synthesis is still not validated until an opt-in live provider run is performed.

---

## Self-Review

Spec coverage:
- The plan addresses a concrete M6 pre-live weakness: provider calls were evidence-ID scoped but not evidence-content informed.
- It keeps the provider bounded to one target file and one allowed file list.
- It does not introduce live network calls or broaden runtime authority.

Placeholder scan:
- No placeholders or deferred implementation steps are present.

Type consistency:
- `EditProposalEvidenceContext` is created in contracts, rendered by provider prompt code, and populated by provider patch planning.
