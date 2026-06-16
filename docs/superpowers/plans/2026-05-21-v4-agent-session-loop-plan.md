# v4 Agent Session Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local `agent-session` command/API that can prepare/load repo context, answer a grounded question, and optionally run a bounded edit/verify task in one user-facing flow.

**Architecture:** Build a thin orchestrator over existing v4 `run_read_only_query` and `run_agent_task` instead of creating a new agent brain. The session command uses one base run id, separate Windows-safe `-ask` and `-edit` sub-runs, and reuses generated index config from the edit/index-prep path where needed.

**Tech Stack:** Python dataclasses, argparse, existing v4 read-only and agent-task APIs, pytest.

---

## File Structure

- Create `src/homllm_v4/runtime/agent_session.py`
  - Owns `AgentSessionRequest`, `AgentSessionResult`, and `run_agent_session`.
  - Calls injected/default `run_read_only_query` and optionally `run_agent_task`.
  - Returns compact ask/edit/index result metadata for CLI JSON.
- Modify `src/homllm_v4/api.py`
  - Re-export session request/result/run function.
- Modify `src/homllm_v4/cli.py`
  - Add `agent-session` subcommand with read-only args plus optional edit args.
  - Use Gemini preview defaults and existing verification command splitting.
- Create `tests/unit/v4/test_agent_session.py`
  - API test for ask-only and ask-plus-edit orchestration with injected runners.
- Modify `tests/unit/v4/test_cli_api.py`
  - CLI propagation test for `agent-session`.
- Update `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Record first session-like local MVP surface and remaining caveats.

## Task 1: Session API Contract

**Files:**
- Create: `tests/unit/v4/test_agent_session.py`
- Create: `src/homllm_v4/runtime/agent_session.py`
- Modify: `src/homllm_v4/api.py`

- [x] **Step 1: Write failing API tests**

Add tests proving ask-only runs read-only once and ask-plus-edit runs read-only then edit with shared base run ids and propagated index/edit options.

- [x] **Step 2: Run API tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_session.py -q
```

Expected: fail because `homllm_v4.runtime.agent_session` does not exist.

- [x] **Step 3: Implement minimal session API**

Create dataclasses and `run_agent_session`. It must call the injected read-only runner with run id `<base>-ask`; if `edit_intent` is provided, call the injected edit runner with run id `<base>-edit`.

- [x] **Step 4: Run API tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_session.py -q
```

Expected: pass.

## Task 2: CLI Subcommand

**Files:**
- Modify: `src/homllm_v4/cli.py`
- Modify: `tests/unit/v4/test_cli_api.py`

- [x] **Step 1: Write failing CLI test**

Add a test proving `agent-session` passes ask/edit/index/live options into `AgentSessionRequest` and prints combined JSON.

- [x] **Step 2: Run CLI test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_cli_api.py::test_cli_agent_session_prints_combined_json -q
```

Expected: fail because `agent-session` is not a CLI command.

- [x] **Step 3: Implement CLI command**

Add `agent-session` parser and call `run_agent_session`. Edit args stay optional, but if edit intent is provided, verification command and live key env are required.

- [x] **Step 4: Run CLI test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_cli_api.py::test_cli_agent_session_prints_combined_json -q
```

Expected: pass.

## Task 3: Focused Verification And Audit

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [x] **Step 1: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_session.py tests\unit\v4\test_cli_api.py tests\unit\v4\test_agent_task.py tests\unit\v4\test_provider_fixture_cli.py -q
```

Expected: pass.

- [x] **Step 2: Run compile verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py
```

Expected: pass.

- [x] **Step 3: Update active-goal audit**

Record that v4 now has a first session-like command combining grounded ask and optional bounded edit. Caveat: it is still a single CLI invocation, not an interactive REPL or autonomous multi-turn coding agent.
