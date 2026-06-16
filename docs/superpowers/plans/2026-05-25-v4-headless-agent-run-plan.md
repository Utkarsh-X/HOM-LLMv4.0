# v4 Headless Agent Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a headless `homllm-agent run` flow that reuses `run_agent_session`, writes a trajectory artifact, and exposes a stable JSON CLI contract.

**Architecture:** `runtime/agent_run.py` is a thin orchestration wrapper over the existing session path, not a second agent loop. `cli.py` exposes `homllm-agent run`, maps CLI flags into typed request fields, and prints one JSON summary. `session.json` remains the persistent state backbone; `trajectory.json` is an inspectable per-run benchmark artifact.

**Tech Stack:** Python dataclasses, argparse, existing HOM-LLM v4 runtime/session modules, pytest.

---

### Task 1: API Contract And Trajectory Wrapper

**Files:**
- Create: `src/homllm_v4/runtime/agent_run.py`
- Modify: `src/homllm_v4/api.py`
- Test: `tests/unit/v4/test_agent_run.py`

- [x] **Step 1: Write failing API test**

Add `test_run_homllm_agent_writes_trajectory_and_session_state_path` to `tests/unit/v4/test_agent_run.py`. Use a fake `session_runner` returning an `AgentSessionResult`. Assert `run_homllm_agent()` returns the run id, stop reason, session path, trajectory path, and writes JSON with ordered steps: `repo_index`, `grounded_answer`, `bounded_edit`, `verification`.

- [x] **Step 2: Run test and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_run.py::test_run_homllm_agent_writes_trajectory_and_session_state_path -q`

Expected: fail because `homllm_v4.runtime.agent_run` does not exist.

- [x] **Step 3: Implement minimal wrapper**

Create frozen dataclasses `HomllmAgentRunRequest` and `HomllmAgentRunResult`, plus `run_homllm_agent(request)`. It should call injected `session_runner`, write `<artifact_root>/<run_id>/trajectory.json`, and return paths as strings.

- [x] **Step 4: Run test and verify GREEN**

Run the same focused pytest command. Expected: pass.

- [x] **Step 5: Export API**

Re-export `HomllmAgentRunRequest`, `HomllmAgentRunResult`, and `run_homllm_agent` from `src/homllm_v4/api.py`.

### Task 2: CLI Command

**Files:**
- Modify: `src/homllm_v4/cli.py`
- Test: `tests/unit/v4/test_cli_api.py`

- [x] **Step 1: Write failing CLI test**

Add `test_cli_homllm_agent_run_prints_json_summary` to `tests/unit/v4/test_cli_api.py`. Monkeypatch `cli.run_homllm_agent`, invoke `cli.main(("homllm-agent", "run", ...))`, and assert the captured request fields plus JSON output include `command="homllm-agent run"`, `run_id`, `stop_reason`, `session_state_path`, and `trajectory_path`.

- [x] **Step 2: Run test and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_cli_api.py::test_cli_homllm_agent_run_prints_json_summary -q`

Expected: fail because the CLI does not recognize `homllm-agent run`.

- [x] **Step 3: Implement minimal CLI parsing**

Add an argparse `homllm-agent` command with a nested `run` subcommand. Reuse the same flags as `agent-session` for config, workspace, artifacts, query, optional edit, verification, provider, and index preparation. Map into `HomllmAgentRunRequest`.

- [x] **Step 4: Run test and verify GREEN**

Run the same focused pytest command. Expected: pass.

### Task 3: Verification And Audit

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [x] **Step 1: Run focused test suite**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_run.py tests\unit\v4\test_agent_session.py tests\unit\v4\test_cli_api.py -q`

- [x] **Step 2: Run compile check**

Run: `.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py`

- [x] **Step 3: Update active-goal audit**

Record that the headless command skeleton exists and writes trajectory artifacts, but note that the full benchmark suite and Terminal-Bench/Harbor adapter remain incomplete.

- [x] **Step 4: Final verification**

Rerun the focused test suite and compile check after audit edits if code changed after the first verification.
