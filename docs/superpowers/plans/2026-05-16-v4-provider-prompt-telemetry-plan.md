# v4 Provider Prompt Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make provider prompt size and evidence-context truncation visible in v4 telemetry so token-efficiency can be measured before live provider synthesis.

**Architecture:** `ProviderBackedEditProposer` already owns provider prompt construction. Extend that same boundary to compute prompt metadata and merge it into capability telemetry output summaries for both successful and failed provider proposal attempts.

**Tech Stack:** Python dataclasses/private helpers, pytest, existing v4 telemetry contract.

---

## File Structure

- Modify: `src/homllm_v4/planning/provider_edit_proposer.py`
  - Add private prompt metadata structure.
  - Return prompt text plus evidence-context metadata from prompt rendering.
  - Include metadata in success and failure telemetry.
- Modify: `tests/unit/v4/test_provider_edit_proposer.py`
  - Add tests for prompt character count and evidence-context truncation telemetry.
- Modify after verification: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - Record provider prompt telemetry support.
- Modify after verification: `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Record prompt telemetry as token-efficiency measurement support.

---

### Task 1: Red Tests For Provider Prompt Telemetry

**Files:**
- Modify: `tests/unit/v4/test_provider_edit_proposer.py`

- [ ] **Step 1: Add success telemetry test**

Add a test proving successful provider proposal telemetry exposes prompt and evidence-context size:

```python
def test_provider_backed_edit_proposer_reports_prompt_metadata_in_telemetry() -> None:
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
                content="abc",
            ),
        ),
    )

    result = ProviderBackedEditProposer(provider=provider).propose(request)

    assert result.ok is True
    assert result.telemetry.output_summary["prompt_char_count"] > 0
    assert result.telemetry.output_summary["evidence_context_item_count"] == 1
    assert result.telemetry.output_summary["evidence_context_rendered_char_count"] == 3
    assert result.telemetry.output_summary["evidence_context_truncated"] is False
```

- [ ] **Step 2: Add truncation telemetry test**

Add:

```python
def test_provider_backed_edit_proposer_reports_evidence_context_truncation() -> None:
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
                content="abcdefghij",
            ),
        ),
    )

    result = ProviderBackedEditProposer(
        provider=provider,
        max_evidence_item_chars=4,
        max_evidence_context_chars=20,
    ).propose(request)

    assert result.ok is True
    assert result.telemetry.output_summary["evidence_context_rendered_char_count"] == 4
    assert result.telemetry.output_summary["evidence_context_truncated"] is True
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py -q
```

Expected: failures because prompt metadata is not included in telemetry yet.

---

### Task 2: Implement Provider Prompt Metadata

**Files:**
- Modify: `src/homllm_v4/planning/provider_edit_proposer.py`

- [ ] **Step 1: Add private prompt metadata dataclass**

Add:

```python
@dataclass(frozen=True)
class _PromptMetadata:
    prompt_char_count: int
    evidence_context_item_count: int
    evidence_context_rendered_char_count: int
    evidence_context_truncated: bool
```

- [ ] **Step 2: Return prompt metadata from prompt construction**

Add a private helper:

```python
def _build_edit_proposal_prompt_with_metadata(...) -> tuple[str, _PromptMetadata]:
```

Keep public `build_edit_proposal_prompt(...) -> str` backward-compatible by calling the private helper and returning only the prompt text.

- [ ] **Step 3: Collect evidence-context metadata while rendering**

Update evidence rendering to track:
- number of evidence context records supplied;
- number of evidence content characters emitted;
- whether any item or total budget caused truncation.

- [ ] **Step 4: Merge metadata into telemetry output summary**

Pass `prompt_metadata` into `_failed`, `_with_provider_usage`, and `_telemetry`.

Telemetry output summary should include:

```python
{
    "prompt_char_count": ...,
    "evidence_context_item_count": ...,
    "evidence_context_rendered_char_count": ...,
    "evidence_context_truncated": ...,
}
```

- [ ] **Step 5: Run targeted tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py -q
```

Expected: provider edit proposer tests pass.

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
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_prompt_telemetry --artifact-root temp\v4_real_index_provider_patch_runs_prompt_telemetry --run-id real-index-provider-patch-prompt-telemetry-check --smoke-safe
```

Expected:
- `failed_cases=0`
- `passed_cases=9`
- `stop_reason_counts` contains only `verified`.

- [ ] **Step 6: Update audits**

Record:
- provider prompt/evidence context telemetry now exists;
- real live provider token measurements are still pending.

---

## Self-Review

Spec coverage:
- This plan addresses measurement of the bounded provider prompt, which directly supports the token-efficiency thesis.
- It does not alter provider authority, retrieval behavior, patch scope, or verification behavior.

Placeholder scan:
- No placeholders or deferred implementation steps are present.

Type consistency:
- `_PromptMetadata` is private to the provider edit proposer and only appears in telemetry output summaries.
