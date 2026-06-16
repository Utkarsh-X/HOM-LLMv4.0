# V4 Live Provider Expected Behavior Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten live provider prompting so exact expected-behavior examples and verification summaries are treated as mandatory acceptance criteria before returning a patch.

**Architecture:** Keep verification as the runtime gate. Improve the provider proposal prompt by making expected examples explicit contract requirements, so the model must satisfy examples like `truncate_string('abcdef', 2) == 'ab'` rather than applying a plausible but wrong generic fix.

**Tech Stack:** Python, pytest, HOM-LLM v4 provider edit proposer.

---

### Task 1: Prompt Acceptance Criteria Contract

**Files:**
- Modify: `tests/unit/v4/test_provider_edit_proposer.py`
- Modify: `src/homllm_v4/planning/provider_edit_proposer.py`

- [x] **Step 1: Write failing prompt assertions**

In `test_provider_backed_edit_proposer_accepts_valid_json_response`, assert:

```python
assert "Exact examples in Expected behavior are mandatory acceptance criteria" in provider.last_request.prompt
assert "The proposed new_content must satisfy the Verification command" in provider.last_request.prompt
assert "Do not use a plausible generic fix if it violates an exact expected output" in provider.last_request.prompt
```

- [x] **Step 2: Run the failing prompt test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py::test_provider_backed_edit_proposer_accepts_valid_json_response -q
```

Expected: FAIL because these instructions are not present yet.

- [x] **Step 3: Add generic acceptance-criteria prompt instructions**

Add these lines near the expected behavior and verification instructions:

```python
"Exact examples in Expected behavior are mandatory acceptance criteria.",
"The proposed new_content must satisfy the Verification command.",
"Do not use a plausible generic fix if it violates an exact expected output.",
```

- [x] **Step 4: Run provider edit proposer tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py -q
```

Expected: PASS.

### Task 2: Retry Semantic Live Case

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [x] **Step 1: Retry `gemini-3.1-flash-lite-preview` semantic case**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_string_truncate_acceptance --artifact-root temp\v4_real_index_provider_patch_runs_live_string_truncate_acceptance --run-id real-index-provider-patch-live-string-truncate-acceptance-check --edit-provider-mode live --live-provider gemini --live-model gemini-3.1-flash-lite-preview --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id string-truncate-guard --max-prompt-chars 15000 --smoke-safe
```

Expected: The run should either verify or reveal a new concrete failure. It should not repeat the generic `max(0, max_length - len(suffix))` failure.

- [x] **Step 2: Run final verification gates**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected: all pytest/compile commands pass, and the boundary scan prints no matches.

- [x] **Step 3: Update audits**

Record the repeated wrong generic fix, prompt hardening, and retry result.
