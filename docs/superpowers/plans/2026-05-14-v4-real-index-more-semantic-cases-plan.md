# v4 Real-Index Additional Semantic Cases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the real-index provider write benchmark from one semantic case to three semantic cases while staying fake-provider-first and deterministic.

**Architecture:** Extend `run_real_index_provider_patch_suite` with two additional non-no-op cases in `utils/validators.py`. Each case uses real indexed retrieval in CLI runs, fake provider-generated new content, v4 patch application, and focused Python behavior verification.

**Tech Stack:** Python, pytest, v4 evaluation harness, v4 write/verify loop, real v3 retrieval adapter for CLI smoke.

---

## File Structure

- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
  - Add semantic cases:
    - `validate-file-path-drive-guard`
    - `validate-email-local-dot-guard`
  - Add provider transforms and verification commands.
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`
  - Require at least six cases.
  - Assert both new patches are present in copied workspaces.
- Modify audits:
  - `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - `docs/v4_architecture/09-active-goal-completion-audit.md`

---

### Task 1: Add Failing Test Expectations

**Files:**
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [ ] **Step 1: Change expected case count**

Change:

```python
assert result.total_cases >= 4
```

to:

```python
assert result.total_cases >= 6
```

- [ ] **Step 2: Assert new semantic patches exist**

Add assertions for:

```python
validate-file-path-drive-guard/utils/validators.py
```

containing:

```python
"':' in file_path"
```

and:

```python
validate-email-local-dot-guard/utils/validators.py
```

containing:

```python
'".." in local_part'
```

- [ ] **Step 3: Run test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_runs_multiple_cases_with_injected_planner -q
```

Expected: FAIL because the suite currently has only four cases.

---

### Task 2: Implement Two Semantic Cases

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`

- [ ] **Step 1: Add file path case**

Add:

```python
RealIndexProviderPatchCase(
    case_id="validate-file-path-drive-guard",
    target_file="utils/validators.py",
    query="validate_file_path rejects Windows drive absolute paths",
    intent="Reject Windows drive-qualified paths in validate_file_path.",
    expected_behavior="validate_file_path('C:/secret.txt') returns invalid.",
    provider_mode="file_path_drive_guard",
    verification_mode="file_path_drive_guard",
)
```

Transform:

```python
old = "    if '..' in file_path or file_path.startswith('/'):\n        return False, \"Invalid file path\""
new = "    if '..' in file_path or file_path.startswith('/') or file_path.startswith('\\\\') or ':' in file_path:\n        return False, \"Invalid file path\""
```

Verification:

```python
"from utils.validators import validate_file_path; "
"raise SystemExit(0 if not validate_file_path('C:/secret.txt')[0] "
"and not validate_file_path('\\\\secret.txt')[0] else 1)"
```

- [ ] **Step 2: Add email local-dot case**

Add:

```python
RealIndexProviderPatchCase(
    case_id="validate-email-local-dot-guard",
    target_file="utils/validators.py",
    query="validate_email rejects consecutive dots in local part",
    intent="Reject email addresses with consecutive dots before @.",
    expected_behavior="validate_email('a..b@example.com') returns invalid while validate_email('a.b@example.com') remains valid.",
    provider_mode="email_local_dot_guard",
    verification_mode="email_local_dot_guard",
)
```

Transform inserts after the regex match block:

```python
    local_part = email.split('@', 1)[0]
    if '..' in local_part:
        return False, "Invalid email format"
```

Verification:

```python
"from utils.validators import validate_email; "
"raise SystemExit(0 if not validate_email('a..b@example.com')[0] "
"and validate_email('a.b@example.com')[0] else 1)"
```

- [ ] **Step 3: Run targeted test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

Expected: pass.

---

### Task 3: Run Real-Index CLI and Full Verification

- [ ] **Step 1: Run CLI benchmark**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_semantic_3 --artifact-root temp\v4_real_index_provider_patch_runs_semantic_3 --run-id real-index-provider-patch-semantic-3-check --smoke-safe
```

Expected: `6 passed_cases`, `0 failed_cases`.

- [ ] **Step 2: Run full verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

- [ ] **Step 3: Update audits**

Record that the benchmark now has six total cases: three no-op and three semantic non-no-op cases.

---

## Self-Review

Spec coverage:

- Adds broader semantic write coverage without live provider calls.
- Keeps verification behavior-focused.
- Keeps real v3 coupling behind existing adapter path.

Placeholder scan:

- No placeholder task remains.

Type consistency:

- Uses existing case metadata fields and transform/verification selector structure.

