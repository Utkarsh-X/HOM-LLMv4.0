# V4 Real-Index Provider Prompt Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a no-provider-call prompt preflight path for `eval-real-index-provider-patch` so live-provider runs can inspect case selection, prompt size, evidence-context size, and key presence before spending an API call.

**Architecture:** The preflight path should reuse the existing real-index provider patch suite with `max_prompt_chars=0`, which forces `ProviderBackedEditProposer` to build and persist the exact prompt, then stop with `provider_prompt_budget_exceeded` before invoking any provider. A small CLI wrapper converts that expected structured failure into a successful preflight JSON report.

**Tech Stack:** Python, argparse CLI, pytest, HOM-LLM v4 real-index provider patch suite.

---

### Task 1: CLI Prompt Preflight Mode

**Files:**
- Modify: `src/homllm_v4/cli.py`
- Modify: `tests/unit/v4/test_provider_fixture_cli.py`

- [x] **Step 1: Write the failing CLI test**

Add a test that monkeypatches `run_real_index_provider_patch_suite`, invokes:

```text
eval-real-index-provider-patch --prompt-preflight --edit-provider-mode live --live-api-key-env HOMLLM_TEST_KEY --case-id admin-routes-noop ...
```

Assert:

```python
assert result == 0
assert captured["max_prompt_chars"] == 0
assert captured["edit_provider_mode"] == "fake"
assert payload["preflight_only"] is True
assert payload["requested_edit_provider_mode"] == "live"
assert payload["live_api_key_present"] is True
assert payload["summary_metrics"]["numeric_metric_totals"]["prompt_char_count"] == 1234
```

- [x] **Step 2: Run the failing CLI test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_runs_real_index_provider_patch_prompt_preflight_without_live_provider_call -q
```

Expected: FAIL because `--prompt-preflight` does not exist.

- [x] **Step 3: Add `--prompt-preflight` argument**

In `src/homllm_v4/cli.py`, add:

```python
real_index_provider_patch.add_argument("--prompt-preflight", action="store_true")
```

- [x] **Step 4: Implement preflight dispatch**

Before normal `run_real_index_provider_patch_suite`, if `args.prompt_preflight` is true:

```python
requested_live_api_key = (
    os.getenv(args.live_api_key_env) if args.live_api_key_env else None
)
result = run_real_index_provider_patch_suite(
    ...,
    edit_provider_mode="fake",
    live_provider_name=args.live_provider,
    live_model=args.live_model,
    live_api_key=None,
    case_ids=tuple(args.case_id) if args.case_id else None,
    max_prompt_chars=0,
)
print(json.dumps({...}, sort_keys=True))
return 0
```

The JSON must include:

```python
{
    "command": args.command,
    "preflight_only": True,
    "requested_edit_provider_mode": args.edit_provider_mode,
    "live_provider": args.live_provider,
    "live_model": args.live_model,
    "live_api_key_env": args.live_api_key_env,
    "live_api_key_present": requested_live_api_key is not None,
    "run_id": result.run_id,
    "total_cases": result.total_cases,
    "artifact_root": str(artifact_root),
    "summary_metrics": result.summary_metrics,
}
```

Catch `ValueError` with the existing structured JSON error behavior.

- [x] **Step 5: Run the focused CLI test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_runs_real_index_provider_patch_prompt_preflight_without_live_provider_call -q
```

Expected: PASS.

### Task 2: Real CLI Smoke

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [x] **Step 1: Run real prompt preflight**

Run:

```powershell
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-real-index-provider-patch --prompt-preflight --config configs\agentic\ccg_stage2_canary_v1\ccg_stage2_agentic_ro3.yaml --source-workspace-root test_repo --workspace-root temp\v4_real_index_provider_patch_work_prompt_preflight --artifact-root temp\v4_real_index_provider_patch_runs_prompt_preflight --run-id real-index-provider-patch-prompt-preflight-check --edit-provider-mode live --live-provider gemini --live-model gemini-2.5-flash --case-id admin-routes-noop --smoke-safe
```

Expected: exit code `0`, `preflight_only=true`, `requested_edit_provider_mode=live`, `live_api_key_present=false` unless the environment variable was supplied, and summary metrics include `provider_prompt_budget_exceeded`, `prompt_char_count`, and zero provider tokens.

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

Record prompt-preflight availability and smoke output in both audit docs.
