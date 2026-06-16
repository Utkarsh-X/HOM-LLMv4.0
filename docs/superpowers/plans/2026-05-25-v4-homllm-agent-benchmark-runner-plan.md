# v4 homllm-agent Benchmark Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local 10-case benchmark runner that executes `homllm-agent run`, consumes `trajectory.json`, and produces an `EvaluationRunResult` summary.

**Architecture:** `evaluation/agent_benchmark.py` owns benchmark case definitions, workspace copy isolation, headless-agent invocation, trajectory parsing, and summary aggregation. It reuses `HomllmAgentRunRequest` and `EvaluationRunResult` instead of introducing a parallel benchmark result type. The CLI gets an `eval-homllm-agent` command for listing and running the internal suite.

**Tech Stack:** Python dataclasses, pathlib/shutil/json, HOM-LLM v4 runtime contracts, argparse, pytest.

---

### Task 1: Benchmark Runner Contract

**Files:**
- Create: `src/homllm_v4/evaluation/agent_benchmark.py`
- Modify: `src/homllm_v4/api.py`
- Test: `tests/unit/v4/test_agent_benchmark.py`

- [x] **Step 1: Write failing suite-size test**

Add `test_internal_agent_benchmark_suite_has_mvp_case_count` proving the default internal suite exposes between 10 and 20 cases and each case has a query, expected stop reason, and verification argv.

- [x] **Step 2: Run test and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_benchmark.py::test_internal_agent_benchmark_suite_has_mvp_case_count -q`

Expected: fail because `homllm_v4.evaluation.agent_benchmark` does not exist.

- [x] **Step 3: Write failing runner test**

Add `test_run_homllm_agent_benchmark_aggregates_trajectory_metrics`. Use two selected case IDs, a fake `agent_runner` that writes per-case `trajectory.json`, and assert `EvaluationRunResult.total_cases`, pass counts, stop reason counts, numeric totals, categorical trajectory status counts, and `evaluation/summary.json`.

- [x] **Step 4: Implement minimal runner**

Create `AgentBenchmarkCase`, `INTERNAL_AGENT_BENCHMARK_CASES`, `agent_benchmark_case_metadata`, and `run_homllm_agent_benchmark`. The runner copies `source_workspace_root` to `<workspace_root>/<run_id>/cases/<case_id>`, invokes `run_homllm_agent`, reads `trajectory.json`, aggregates selected metrics, writes `evaluation/summary.json`, and returns `EvaluationRunResult`.

- [x] **Step 5: Run tests and verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_benchmark.py -q`

Expected: pass.

### Task 2: CLI Wiring

**Files:**
- Modify: `src/homllm_v4/cli.py`
- Test: `tests/unit/v4/test_cli_api.py`

- [x] **Step 1: Write failing CLI list/run tests**

Add a CLI list test for `eval-homllm-agent --list-cases` and a run test with a monkeypatched `run_homllm_agent_benchmark`, asserting JSON output and request propagation.

- [x] **Step 2: Run tests and verify RED**

Run the two focused CLI tests. Expected: fail because `eval-homllm-agent` does not exist.

- [x] **Step 3: Implement CLI**

Add parser flags: `--config`, `--source-workspace-root`, `--workspace-root`, `--artifact-root`, `--run-id`, `--list-cases`, `--case-id`, live provider flags, prompt/repair/index flags, and summary JSON output.

- [x] **Step 4: Run tests and verify GREEN**

Run the focused CLI tests. Expected: pass.

### Task 3: Verification And Audit

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [x] **Step 1: Run focused verification**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_benchmark.py tests\unit\v4\test_agent_run.py tests\unit\v4\test_cli_api.py -q`

- [x] **Step 2: Run compile check**

Run: `.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py`

- [x] **Step 3: Update audit**

Record that a 10-case internal benchmark runner now exists around `homllm-agent run`, but live Gemini benchmark evidence remains opt-in/not yet executed for this slice.
