# v4 Agent Task Auto Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `agent-task` prepare a repo index/config before running the bounded edit/verify loop.

**Architecture:** Add a small v4 runtime helper that rewrites a template config's v3 index storage paths into a run-local index directory, optionally invokes the v3 `IndexerPipeline`, and returns the generated config path. Wire it into `run_agent_task` behind an opt-in flag so the existing prebuilt-config path remains unchanged.

**Tech Stack:** Python dataclasses, PyYAML, existing v3 `Config`/`IndexerPipeline`, argparse, pytest.

---

## File Structure

- Create `src/homllm_v4/runtime/agent_index.py`
  - Owns `AgentIndexPrepRequest`, `AgentIndexPrepResult`, and `prepare_agent_task_index`.
  - Rewrites `indexer.storage` paths in a copied config.
  - Calls an injectable index builder, defaulting to v3 `IndexerPipeline`.
- Modify `src/homllm_v4/runtime/agent_task.py`
  - Add opt-in index prep fields to `AgentTaskRequest`.
  - Use the generated config path when index prep is enabled.
  - Return index prep evidence in `AgentTaskResult`.
- Modify `src/homllm_v4/cli.py`
  - Add `--prepare-index`, `--index-artifact-dir`, `--index-incremental`, and `--index-skip-vectors`.
  - Include generated index paths in JSON output.
- Modify `tests/unit/v4/test_agent_task.py`
  - Add API test with an injected fake index builder.
- Modify `tests/unit/v4/test_provider_fixture_cli.py`
  - Add CLI propagation test for index prep flags.
- Update `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Record auto-index/load progress and caveats after verification.

## Task 1: Index Prep Helper

**Files:**
- Create: `src/homllm_v4/runtime/agent_index.py`
- Test: `tests/unit/v4/test_agent_task.py`

- [x] **Step 1: Write the failing index prep API test**

Add a test proving `run_agent_task` can generate a run-local config and call an injected index builder before planning.

- [x] **Step 2: Run the test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_task.py::test_run_agent_task_can_prepare_run_local_index_config -q
```

Expected: fail because `AgentTaskRequest` has no index-prep fields and no helper exists.

- [x] **Step 3: Implement minimal helper and API wiring**

Create `agent_index.py`, load the template config as YAML, rewrite storage paths to `<artifact_root>/<run_id>/index`, write `generated_config.yaml`, invoke the injectable/default builder, and return result metadata.

- [x] **Step 4: Run the test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_task.py::test_run_agent_task_can_prepare_run_local_index_config -q
```

Expected: pass.

## Task 2: CLI Wiring

**Files:**
- Modify: `src/homllm_v4/cli.py`
- Test: `tests/unit/v4/test_provider_fixture_cli.py`

- [x] **Step 1: Write the failing CLI propagation test**

Add a test proving `agent-task --prepare-index --index-skip-vectors` reaches `AgentTaskRequest`.

- [x] **Step 2: Run the CLI test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_runs_agent_task_with_index_prep_flags -q
```

Expected: fail because the CLI does not accept index prep flags.

- [x] **Step 3: Implement CLI flags and JSON output**

Add flags, pass them to `AgentTaskRequest`, and print `index_built`, `index_config_path`, and `index_artifact_paths`.

- [x] **Step 4: Run the CLI test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_runs_agent_task_with_index_prep_flags -q
```

Expected: pass.

## Task 3: Focused Verification And Audit

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [x] **Step 1: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_task.py tests\unit\v4\test_provider_fixture_cli.py -q
```

Expected: pass.

- [x] **Step 2: Run compile verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py
```

Expected: pass.

- [x] **Step 3: Update active-goal audit**

Record that `agent-task` can now prepare a run-local index/config before invoking the edit loop. Caveat: this is still a local command flow, not a full interactive session manager.
