# V4 Provider Newline Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent live provider whole-file patches from dropping a final newline when the original target file had one.

**Architecture:** `ProviderProposedPatchPlanner` has both the fresh direct-read content and the provider proposed full-file content. Before passing `new_content` into `EvidenceBackedPatchPlanner`, normalize only the safe case: if old content ends with `\n` and proposed content does not, append one newline. Do not otherwise rewrite provider output.

**Tech Stack:** Python, pytest, HOM-LLM v4 provider patch planner.

---

### Task 1: Preserve Trailing Newline

**Files:**
- Modify: `tests/unit/v4/test_provider_patch_planner.py`
- Modify: `src/homllm_v4/planning/provider_patch_planner.py`

- [x] **Step 1: Write failing regression**

Add a test where the original file ends with `\n`, the fake provider returns valid full-file content without the trailing newline, and assert:

```python
assert result.output.patch_request.patches[0].new_content.endswith("\n")
```

- [x] **Step 2: Run the failing test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_patch_planner.py::test_provider_proposed_patch_planner_preserves_original_trailing_newline -q
```

Expected: FAIL because provider output currently flows through unchanged.

- [x] **Step 3: Implement normalization**

Add:

```python
def _preserve_original_trailing_newline(new_content: str, old_content: str) -> str:
    if old_content.endswith("\n") and not new_content.endswith("\n"):
        return f"{new_content}\n"
    return new_content
```

Use this helper when constructing `EvidenceBackedPatchPlanRequest`.

- [x] **Step 4: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_patch_planner.py -q
```

Expected: PASS.

- [x] **Step 5: Run final verification gates**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected: all pytest/compile commands pass, and the boundary scan prints no matches.
