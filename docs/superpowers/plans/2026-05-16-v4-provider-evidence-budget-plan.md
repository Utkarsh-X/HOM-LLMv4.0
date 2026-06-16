# v4 Provider Evidence Prompt Budget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep provider prompts evidence-informed without allowing retrieved evidence context to grow unbounded.

**Architecture:** Add explicit prompt-budget knobs to `ProviderBackedEditProposer`. Prompt rendering truncates each evidence item and stops adding evidence when the total evidence-context budget is exhausted, preserving token-efficiency before live provider synthesis.

**Tech Stack:** Python dataclasses/protocols, pytest, existing v4 provider edit proposer.

---

## File Structure

- Modify: `src/homllm_v4/planning/provider_edit_proposer.py`
  - Add prompt-budget constructor parameters.
  - Pass budget values into prompt construction.
  - Truncate evidence context deterministically.
- Modify: `tests/unit/v4/test_provider_edit_proposer.py`
  - Add red tests for per-item and total evidence-context truncation.
- Modify after verification: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - Record bounded evidence prompt support.
- Modify after verification: `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Record this as token-efficiency hardening before live synthesis.

---

### Task 1: Red Tests For Prompt Budgeting

**Files:**
- Modify: `tests/unit/v4/test_provider_edit_proposer.py`

- [ ] **Step 1: Add per-item truncation test**

Add:

```python
def test_provider_backed_edit_proposer_truncates_long_evidence_context_items() -> None:
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
    assert provider.last_request is not None
    assert "abcd\n[truncated]" in provider.last_request.prompt
    assert "abcdefghij" not in provider.last_request.prompt
```

- [ ] **Step 2: Add total evidence budget test**

Add:

```python
def test_provider_backed_edit_proposer_limits_total_evidence_context_chars() -> None:
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
        evidence_ids=("cand-1", "cand-2"),
        allowed_file_paths=("calculator.py",),
        verification_summary="pytest . -q",
        evidence_context=(
            EditProposalEvidenceContext(
                evidence_id="cand-1",
                file_path="calculator.py",
                span_start=1,
                span_end=2,
                content="first evidence",
            ),
            EditProposalEvidenceContext(
                evidence_id="cand-2",
                file_path="calculator.py",
                span_start=3,
                span_end=4,
                content="second evidence",
            ),
        ),
    )

    result = ProviderBackedEditProposer(
        provider=provider,
        max_evidence_item_chars=100,
        max_evidence_context_chars=5,
    ).propose(request)

    assert result.ok is True
    assert provider.last_request is not None
    assert "first" in provider.last_request.prompt
    assert "second evidence" not in provider.last_request.prompt
    assert "[evidence context budget exhausted]" in provider.last_request.prompt
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py -q
```

Expected: failures because `ProviderBackedEditProposer` does not accept prompt-budget constructor arguments yet.

---

### Task 2: Implement Bounded Evidence Prompt Rendering

**Files:**
- Modify: `src/homllm_v4/planning/provider_edit_proposer.py`

- [ ] **Step 1: Add constructor budget fields**

Add optional parameters:

```python
max_evidence_item_chars: int = 2000
max_evidence_context_chars: int = 12000
```

Store them as normalized positive integers.

- [ ] **Step 2: Pass budget into prompt builder**

Change:

```python
prompt = build_edit_proposal_prompt(request)
```

to:

```python
prompt = build_edit_proposal_prompt(
    request,
    max_evidence_item_chars=self.max_evidence_item_chars,
    max_evidence_context_chars=self.max_evidence_context_chars,
)
```

- [ ] **Step 3: Truncate evidence context deterministically**

Update `_render_evidence_context` to:
- return `Evidence context: none supplied` when empty;
- truncate each item to `max_evidence_item_chars`;
- decrement remaining total context budget by emitted content length;
- emit `[evidence context budget exhausted]` when later items cannot fit.

- [ ] **Step 4: Run targeted tests and verify GREEN**

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
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_evidence_budget --artifact-root temp\v4_real_index_provider_patch_runs_evidence_budget --run-id real-index-provider-patch-evidence-budget-check --smoke-safe
```

Expected:
- `failed_cases=0`
- `passed_cases=9`
- `stop_reason_counts` contains only `verified`.

- [ ] **Step 6: Update audits**

Record:
- provider prompts include evidence context under explicit per-item and total prompt budgets;
- live LLM synthesis is still not validated.

---

## Self-Review

Spec coverage:
- This plan directly protects the HOM-LLM token-efficiency thesis after adding provider evidence context.
- It leaves provider execution, file authority, retrieval, and patching behavior unchanged.

Placeholder scan:
- No placeholders or deferred implementation steps are present.

Type consistency:
- Budget knobs live on `ProviderBackedEditProposer` and are passed into `build_edit_proposal_prompt` and `_render_evidence_context`.
