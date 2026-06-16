# V4 Live Provider Output Budget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make live provider output-budget failures explicit and configurable before retrying live patch synthesis.

**Architecture:** Provider response parsing should distinguish malformed JSON from provider truncation using the `finish_reason` metadata already carried by `V3ProviderEditProposalAdapter`. The real-index provider patch CLI should expose a bounded `--live-max-output-tokens` knob and pass it to the v3 provider adapter factory, instead of using an invisible fixed budget.

**Tech Stack:** Python, argparse CLI, pytest, HOM-LLM v4 provider adapter seam.

---

### Task 1: Truncated Provider Response Error Code

**Files:**
- Modify: `tests/unit/v4/test_provider_edit_proposer.py`
- Modify: `src/homllm_v4/planning/provider_edit_proposer.py`

- [x] **Step 1: Write failing truncation test**

Add a provider test with `metadata={"finish_reason": "max_tokens"}` and incomplete JSON. Assert:

```python
assert result.ok is False
assert result.error.code == "provider_response_truncated"
assert result.error.details["finish_reason"] == "max_tokens"
```

- [x] **Step 2: Run the failing test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py::test_provider_backed_edit_proposer_reports_truncated_response_separately -q
```

Expected: FAIL because current code returns `provider_response_invalid`.

- [x] **Step 3: Implement truncation classification**

In `ProviderBackedEditProposer.propose`, before returning `provider_response_invalid` on parse errors, check:

```python
finish_reason = str(provider_response.metadata.get("finish_reason", "")).lower()
if finish_reason in {"max_tokens", "length"}:
    code = "provider_response_truncated"
    details = {"finish_reason": finish_reason}
else:
    code = "provider_response_invalid"
```

Pass details into `_failed`.

- [x] **Step 4: Run provider edit proposer tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py -q
```

Expected: PASS.

### Task 2: CLI Live Max Output Tokens

**Files:**
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`
- Modify: `src/homllm_v4/cli.py`
- Modify: `tests/unit/v4/test_provider_fixture_cli.py`
- Modify: `tests/unit/v4/test_real_index_provider_patch_suite.py`

- [x] **Step 1: Write failing CLI propagation test**

Extend `test_cli_runs_real_index_provider_patch_suite` with:

```text
--live-max-output-tokens 8192
```

Assert:

```python
assert captured["live_max_output_tokens"] == 8192
```

- [x] **Step 2: Write failing suite builder test**

Extend `test_real_index_provider_patch_suite_can_use_injected_live_provider_builder` to pass:

```python
live_max_output_tokens=8192
```

Assert:

```python
assert calls[0]["max_output_tokens"] == 8192
```

- [x] **Step 3: Run failing tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_runs_real_index_provider_patch_suite tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_can_use_injected_live_provider_builder -q
```

Expected: FAIL because the argument and suite parameter do not exist.

- [x] **Step 4: Implement propagation**

Add `live_max_output_tokens: int = 2048` to `run_real_index_provider_patch_suite`, `_build_edit_provider`, and the live provider builder call.

Add CLI argument:

```python
real_index_provider_patch.add_argument("--live-max-output-tokens", type=int, default=2048)
```

Pass `live_max_output_tokens=args.live_max_output_tokens` in normal live mode. Prompt preflight can also pass the value through for reporting consistency, though fake mode will not use it.

- [x] **Step 5: Run focused propagation tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_runs_real_index_provider_patch_suite tests\unit\v4\test_real_index_provider_patch_suite.py::test_real_index_provider_patch_suite_can_use_injected_live_provider_builder -q
```

Expected: PASS.

### Task 3: Retry Live Smoke With Larger Output Budget

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [x] **Step 1: Retry single live case**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_live_single_budget8192 --artifact-root temp\v4_real_index_provider_patch_runs_live_single_budget8192 --run-id real-index-provider-patch-live-single-budget8192-check --edit-provider-mode live --live-provider gemini --live-model gemini-2.5-flash --live-api-key-env GOOGLE_API_KEY --live-max-output-tokens 8192 --case-id admin-routes-noop --max-prompt-chars 15000 --smoke-safe
```

Expected: The run should no longer fail as generic invalid JSON due to max-token truncation. It may verify or fail with a later structured code.

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

Record the live max-token failure, the new error code, output-budget CLI, and retry result.
