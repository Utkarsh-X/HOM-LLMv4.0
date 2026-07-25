# Expanded Multi-Case Live Gemini Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute and evaluate an expanded 3-case live Gemini benchmark suite (`admin-routes-compile`, `string-truncate-guard`, `validate-email-local-dot-guard`) to measure real LLM patch generation quality, verification loop accuracy, and token metrics end-to-end.

**Tech Stack:** Python 3, Gemini 3.1 Flash Lite (via `GOOGLE_API_KEY`), HOM-LLM v4 agent benchmark harness (`eval-homllm-agent`).

---

### Task 1: Execute 3-Case Live Gemini Benchmark Suite

- [ ] **Step 1: Launch benchmark runner via CLI**
  Execute `eval-homllm-agent` with `--answer-provider-mode live`, targeting case IDs `admin-routes-compile`, `string-truncate-guard`, and `validate-email-local-dot-guard` under run ID `live-suite-3case`.
  ```bash
  .\.venv\Scripts\python.exe runtime\v4_cli.py eval-homllm-agent --config configs/default.yaml --source-workspace-root test_repo --workspace-root temp/v4_work --artifact-root temp/v4_runs --run-id live-suite-3case --case-id admin-routes-compile --case-id string-truncate-guard --case-id validate-email-local-dot-guard --live-api-key-env GOOGLE_API_KEY --answer-provider-mode live
  ```

- [ ] **Step 2: Inspect execution logs and summary artifact**
  Parse `temp/v4_runs/live-suite-3case/evaluation/summary.json` to verify total cases, passed cases, failed cases, and per-case trajectory metrics.

- [ ] **Step 3: Analyze patch quality and repair attempt counts**
  Inspect generated patch files and trajectories under `temp/v4_runs/live-suite-3case/` to evaluate code synthesis precision and verify whether any repair attempts were triggered.

---

### Task 2: Document Results and System Benchmark Status

- [ ] **Step 1: Update walkthrough.md and task.md**
  Summarize the multi-case benchmark results, passed/failed breakdown, token averages, and trajectory metrics in `walkthrough.md` and `task.md`.
