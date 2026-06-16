# v4 Persistent Session State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable `session.json` state for the headless MVP runner so future turns, trajectories, and benchmarks can reuse repo/index/run metadata instead of being isolated one-shot commands.

**Architecture:** Create a focused runtime module that owns session metadata and append-only turn records. It should not run providers, modify files, or execute commands; it only persists typed state atomically under the artifact root. `agent-session` will append a turn after ask/edit execution, giving us immediate value while keeping the later `homllm-agent run` loop separate.

**Tech Stack:** Python dataclasses, pathlib, JSON serialization, pytest, existing `homllm_v4.serialization.json.to_jsonable`.

---

## File Structure

- Create `src/homllm_v4/runtime/session_state.py`
  - Defines `AgentSessionState`, `AgentSessionTurn`, `AgentSessionStore`, and helpers.
  - Writes `<artifact_root>/<session_id>/session.json` atomically.
  - Supports create/load/append turn/update index metadata.
  - Rejects paths escaping the configured artifact root.
- Modify `src/homllm_v4/runtime/agent_session.py`
  - Add optional `persist_session_state` flag defaulting to `True`.
  - Append one turn to session state after a successful `run_agent_session` result is composed.
  - Include ask/edit run IDs, stop reasons, answer status, index metadata, and metrics.
- Modify `src/homllm_v4/api.py`
  - Re-export session state contracts.
- Create `tests/unit/v4/test_session_state.py`
  - Tests atomic create/load/append behavior and path containment.
- Modify `tests/unit/v4/test_agent_session.py`
  - Test that `run_agent_session` persists a turn by default and can opt out.
- Update `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Record session-state evidence and remaining gap: no full headless multi-step runner yet.

## Task 1: Session State Store

**Files:**
- Create: `tests/unit/v4/test_session_state.py`
- Create: `src/homllm_v4/runtime/session_state.py`

- [x] **Step 1: Write failing create/load/append test**

Add a test proving `AgentSessionStore.create_or_load(...)` creates `session.json`, preserves workspace/config/artifact metadata, and `append_turn(...)` increments turn numbers while preserving previous turns.

- [x] **Step 2: Run test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_session_state.py::test_session_store_creates_loads_and_appends_turns -q
```

Expected: fail because `homllm_v4.runtime.session_state` does not exist.

- [x] **Step 3: Implement minimal session store**

Implement dataclasses and `AgentSessionStore` with atomic JSON writes using a temporary sibling file and `replace()`.

- [x] **Step 4: Run test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_session_state.py::test_session_store_creates_loads_and_appends_turns -q
```

Expected: pass.

- [x] **Step 5: Add path containment and index metadata tests**

Add tests proving:

- session IDs cannot escape artifact root
- `update_index_metadata(...)` persists generated config paths, artifact paths, and metrics

- [x] **Step 6: Run session state tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_session_state.py -q
```

Expected: pass.

## Task 2: Agent Session Persistence

**Files:**
- Modify: `tests/unit/v4/test_agent_session.py`
- Modify: `src/homllm_v4/runtime/agent_session.py`
- Modify: `src/homllm_v4/api.py`

- [x] **Step 1: Write failing persistence test**

Add a test proving `run_agent_session` writes `<artifact_root>/<run_id>/session.json` with one turn containing query, ask run id, answer text, answer provider mode, edit run id, edit stop reason, index metadata, and metrics.

- [x] **Step 2: Run test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_session.py::test_run_agent_session_persists_session_turn_state -q
```

Expected: fail because `run_agent_session` does not persist session state.

- [x] **Step 3: Implement session persistence**

Create/load `AgentSessionStore` after the result object is composed. Append a turn with current result metadata. Preserve existing CLI output shape.

- [x] **Step 4: Run persistence test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_session.py::test_run_agent_session_persists_session_turn_state -q
```

Expected: pass.

- [x] **Step 5: Add opt-out test**

Add a test proving `persist_session_state=False` does not write `session.json`; this keeps injected tests and future benchmark modes controllable.

- [x] **Step 6: Run agent-session tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_session.py -q
```

Expected: pass.

## Task 3: Verification And Audit

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify: this plan file

- [x] **Step 1: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_session_state.py tests\unit\v4\test_agent_session.py tests\unit\v4\test_cli_api.py tests\unit\v4\test_grounded_answer.py -q
```

Expected: pass.

- [x] **Step 2: Run compile verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py
```

Expected: pass.

- [x] **Step 3: Update audit and plan checkboxes**

Record that persistent session state exists and that the next missing MVP piece is the actual headless multi-step `homllm-agent run` loop using this state.
