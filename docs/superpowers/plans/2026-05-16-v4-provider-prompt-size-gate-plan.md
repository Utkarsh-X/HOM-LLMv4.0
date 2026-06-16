# v4 Provider Prompt Size Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent live provider calls when the assembled provider prompt exceeds an explicit maximum size.

**Architecture:** `ProviderBackedEditProposer` already owns prompt construction and provider invocation. Add a constructor-level `max_prompt_chars` policy, check the built prompt before `_write_response_artifact` or `provider.propose_edit`, and return a structured `provider_prompt_budget_exceeded` failure with prompt telemetry. Prompt artifact writing remains allowed so oversized prompts can be inspected without spending provider tokens.

**Tech Stack:** Python dataclasses/protocols, pytest, existing v4 provider edit proposal telemetry.

---

## File Structure

- Modify: `src/homllm_v4/planning/provider_edit_proposer.py`
  - Add `max_prompt_chars` to `ProviderBackedEditProposer`.
  - Fail before provider invocation when `prompt_char_count > max_prompt_chars`.
  - Include `max_prompt_chars` and `prompt_char_count` in structured error details.
- Modify: `tests/unit/v4/test_provider_edit_proposer.py`
  - Add a red test that an oversized prompt returns `provider_prompt_budget_exceeded` and does not call the fake provider.
- Modify after verification: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - Record prompt-size gate support.
- Modify after verification: `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Record this as live-provider cost safety.

---

### Task 1: Red Test For Prompt Size Gate

**Files:**
- Modify: `tests/unit/v4/test_provider_edit_proposer.py`

- [ ] **Step 1: Add oversized-prompt test**

Add:

```python
def test_provider_backed_edit_proposer_rejects_prompt_over_size_limit_without_calling_provider() -> None:
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Should not be called.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )

    result = ProviderBackedEditProposer(
        provider=provider,
        max_prompt_chars=10,
    ).propose(proposal_request())

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "provider_prompt_budget_exceeded"
    assert provider.last_request is None
    assert result.error.details["max_prompt_chars"] == 10
    assert result.error.details["prompt_char_count"] > 10
    assert result.telemetry.output_summary["prompt_char_count"] > 10
```

- [ ] **Step 2: Run targeted test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py -q
```

Expected: failure because `max_prompt_chars` is not accepted by the constructor.

---

### Task 2: Implement Prompt Size Gate

**Files:**
- Modify: `src/homllm_v4/planning/provider_edit_proposer.py`

- [ ] **Step 1: Add constructor field**

Add:

```python
max_prompt_chars: int | None = None
```

Store:

```python
self.max_prompt_chars = None if max_prompt_chars is None else max(1, int(max_prompt_chars))
```

- [ ] **Step 2: Check before provider invocation**

After writing prompt artifact and before `self.provider.propose_edit`, add:

```python
if self.max_prompt_chars is not None and prompt_build.prompt_char_count > self.max_prompt_chars:
    return _failed(
        request=request,
        started=started,
        provider_response=None,
        prompt_build=prompt_build,
        code="provider_prompt_budget_exceeded",
        message="provider prompt exceeds configured maximum size",
        details={
            "prompt_char_count": prompt_build.prompt_char_count,
            "max_prompt_chars": self.max_prompt_chars,
        },
        artifacts=artifacts,
    )
```

- [ ] **Step 3: Run targeted tests and verify GREEN**

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

- [ ] **Step 1: Run provider/planner tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py tests\unit\v4\test_provider_patch_planner.py -q
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

- [ ] **Step 4: Run real-index CLI benchmark**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_prompt_size_gate --artifact-root temp\v4_real_index_provider_patch_runs_prompt_size_gate --run-id real-index-provider-patch-prompt-size-gate-check --smoke-safe
```

Expected:
- `passed_cases=13`
- `failed_cases=0`
- `baseline_case_count=10`
- `stop_reason_counts={"verified":13}`

- [ ] **Step 5: Update audits**

Record:
- provider prompt-size gate exists;
- oversized prompt failures happen before provider calls;
- live provider synthesis remains unrun.

---

## Self-Review

Spec coverage:
- This directly reduces live-provider token-spend risk.
- It does not change retrieval, patch authority, command execution, or benchmark case behavior.

Placeholder scan:
- No placeholders or deferred implementation steps are present.

Type consistency:
- `max_prompt_chars` is owned by `ProviderBackedEditProposer`, and oversized failures reuse `_failed` telemetry output.
