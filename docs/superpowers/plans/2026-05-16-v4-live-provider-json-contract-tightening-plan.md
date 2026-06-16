# V4 Live Provider JSON Contract Tightening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten the provider prompt after live Gemini returned invalid JSON using a Python-style triple-quoted `new_content`, and reduce unnecessary edits for no-op validation cases.

**Architecture:** Keep parser strict: provider output must be valid JSON. Improve the prompt contract instead of accepting non-JSON dialects. Add explicit instructions that `new_content` must be a JSON string with escaped newlines/quotes and that no-op/validation tasks should return the exact current file content unchanged.

**Tech Stack:** Python, pytest, HOM-LLM v4 provider edit proposer.

---

### Task 1: Prompt Valid-JSON String Contract

**Files:**
- Modify: `tests/unit/v4/test_provider_edit_proposer.py`
- Modify: `src/homllm_v4/planning/provider_edit_proposer.py`

- [x] **Step 1: Write failing prompt assertions**

In `test_provider_backed_edit_proposer_accepts_valid_json_response`, assert the generated prompt includes:

```python
assert "new_content must be a valid JSON string with escaped newlines and quotes" in provider.last_request.prompt
assert "Do not use Python triple-quoted strings" in provider.last_request.prompt
assert "For no-op or validation-only tasks, return current content unchanged" in provider.last_request.prompt
```

- [x] **Step 2: Run the failing prompt test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py::test_provider_backed_edit_proposer_accepts_valid_json_response -q
```

Expected: FAIL because the prompt lacks these live-hardening instructions.

- [x] **Step 3: Add explicit prompt instructions**

Add these lines near the existing `new_content` instructions:

```python
"new_content must be a valid JSON string with escaped newlines and quotes.",
"Do not use Python triple-quoted strings for new_content.",
"For no-op or validation-only tasks, return current content unchanged.",
```

- [x] **Step 4: Run provider edit proposer tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py -q
```

Expected: PASS.

### Task 2: Retry Live No-Op Case

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [x] **Step 1: Retry single live case**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_single_json_contract --artifact-root temp\v4_real_index_provider_patch_runs_live_single_json_contract --run-id real-index-provider-patch-live-single-json-contract-check --edit-provider-mode live --live-provider gemini --live-model gemini-2.5-flash --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id admin-routes-noop --max-prompt-chars 15000 --smoke-safe
```

Expected: The run should not fail because of Markdown fencing, max-token truncation, or Python triple-quoted `new_content`.

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

Record the invalid triple-quoted JSON live failure, prompt hardening, and retry result.
