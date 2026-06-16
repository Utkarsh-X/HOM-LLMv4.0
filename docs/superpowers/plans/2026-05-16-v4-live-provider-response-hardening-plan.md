# V4 Live Provider Response Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden provider edit proposal handling based on the first live Gemini smoke: accept fenced JSON responses and make the prompt explicitly require complete full-file `new_content`.

**Architecture:** `ProviderBackedEditProposer` owns provider response parsing and prompt construction. The parser should normalize common model wrappers such as ```json fences before JSON decoding, while still rejecting non-JSON text. The prompt should state that `new_content` is the complete replacement content for the target file, not a snippet or diff.

**Tech Stack:** Python, pytest, HOM-LLM v4 provider edit proposer.

---

### Task 1: Accept Markdown-Fenced JSON

**Files:**
- Modify: `tests/unit/v4/test_provider_edit_proposer.py`
- Modify: `src/homllm_v4/planning/provider_edit_proposer.py`

- [x] **Step 1: Write the failing parser regression**

Add:

```python
def test_provider_backed_edit_proposer_accepts_markdown_fenced_json_response() -> None:
    provider = FakeProvider(
        response_text=(
            "```json\n"
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use addition.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
            "\n```"
        )
    )

    result = ProviderBackedEditProposer(provider=provider).propose(proposal_request())

    assert result.ok is True
    assert result.output is not None
    assert result.output.target_file == "calculator.py"
    assert "return a + b" in result.output.new_content
```

- [x] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py::test_provider_backed_edit_proposer_accepts_markdown_fenced_json_response -q
```

Expected: FAIL with `provider_response_invalid`.

- [x] **Step 3: Implement response normalization**

Add a helper:

```python
def _json_text_from_provider_response(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return stripped
```

Change:

```python
data = json.loads(text)
```

to:

```python
data = json.loads(_json_text_from_provider_response(text))
```

- [x] **Step 4: Run focused parser test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py::test_provider_backed_edit_proposer_accepts_markdown_fenced_json_response -q
```

Expected: PASS.

### Task 2: Prompt Requires Full-File Content

**Files:**
- Modify: `tests/unit/v4/test_provider_edit_proposer.py`
- Modify: `src/homllm_v4/planning/provider_edit_proposer.py`

- [x] **Step 1: Write prompt regression**

Extend an existing prompt test or add:

```python
assert "new_content must be the complete replacement content for the entire target file" in provider.last_request.prompt
assert "Do not return a snippet, diff, patch, or partial function body" in provider.last_request.prompt
```

- [x] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py::test_provider_backed_edit_proposer_accepts_valid_json_response -q
```

Expected: FAIL because the prompt does not yet include the full-file instruction.

- [x] **Step 3: Add explicit prompt instructions**

Add to `_build_edit_proposal_prompt_with_metadata` immediately after the JSON instruction:

```python
"new_content must be the complete replacement content for the entire target file.",
"Do not return a snippet, diff, patch, or partial function body.",
```

- [x] **Step 4: Run provider edit proposer tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py -q
```

Expected: PASS.

### Task 3: Live Smoke Retry

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [x] **Step 1: Retry the single live no-op case**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_single_hardened --artifact-root temp\v4_real_index_provider_patch_runs_live_single_hardened --run-id real-index-provider-patch-live-single-hardened-check --edit-provider-mode live --live-provider gemini --live-model gemini-2.5-flash --live-api-key-env GOOGLE_API_KEY --case-id admin-routes-noop --max-prompt-chars 15000 --smoke-safe
```

Expected: Either `verified` or a later structured failure. It must not fail only because JSON is Markdown-fenced.

- [ ] **Step 2: Run final verification gates**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected: all pytest/compile commands pass, and the boundary scan prints no matches.

- [ ] **Step 3: Update audits**

Record the original live failure, the parser/prompt hardening, and the retry result.
