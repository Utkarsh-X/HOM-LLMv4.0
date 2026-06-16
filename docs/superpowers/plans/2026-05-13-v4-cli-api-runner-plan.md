# v4 CLI API Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal callable API and argparse CLI for running v4 read-only smoke/evaluation flows outside unit tests.

**Architecture:** The CLI remains thin. `api.py` owns callable functions that assemble artifact manager, ledger writer, v3 adapter-backed services, and runtime loops. `cli.py` only parses arguments and prints compact JSON.

**Tech Stack:** Python argparse, pathlib, uuid, v4 serialization, existing v4 runtime/evaluation components.

---

## Files

Create:

- `src/homllm_v4/api.py`
- `src/homllm_v4/cli.py`
- `tests/unit/v4/test_cli_api.py`

## Task 1: API

- [ ] Implement `run_read_only_query(...)`.
- [ ] It accepts config path, workspace root, query, run id, artifact root, max passes, and smoke-safe flag.
- [ ] It returns `ReadOnlyLoopResult`.
- [ ] It persists standard run artifacts through existing runtime.

## Task 2: CLI

- [ ] Implement `python -m homllm_v4.cli read-only ...`.
- [ ] Print JSON with `run_id`, `stop_reason`, `pass_count`, `artifact_root`, and `response_text`.
- [ ] Return process code `0` when the read-only run returns a result without service error; otherwise `1`.

## Task 3: Tests

- [ ] Test API with injected fake component builder to avoid v3 runtime.
- [ ] Test CLI parser with injected API function.
- [ ] Do not run real v3 smoke through the default CLI unit tests.

## Task 4: Verification

- [ ] Run `pytest tests/unit/v4/test_cli_api.py -q`.
- [ ] Run `pytest tests/unit/v4 -q`.
- [ ] Run boundary tests, compileall, and real v3 smoke.

## Explicit Exclusions

- No package console script registration yet.
- No write-verify CLI yet.
- No product UI.
- No LLM generation.
