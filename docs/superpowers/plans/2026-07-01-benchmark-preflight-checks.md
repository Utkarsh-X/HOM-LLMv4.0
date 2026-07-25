# Benchmark Preflight Validation Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add upfront input validation checks (preflight checks) to `run_homllm_agent_benchmark` to verify config paths, source workspace directories, API keys, and workspace directory collisions before starting any test cases.

**Architecture:** We will inject validation checks at the very beginning of the `run_homllm_agent_benchmark` function. These checks will verify inputs and raise clear, structured `ValueError` exceptions. The CLI layer already catches `ValueError` and outputs clean JSON error messages.

**Tech Stack:** Python 3, Pytest.

---

### Task 1: Add Regression Tests in test_agent_benchmark.py

**Files:**
- Modify: [test_agent_benchmark.py](file:///E:/HOM-LLM(v3.0)/tests/unit/v4/test_agent_benchmark.py)

- [ ] **Step 1: Write the failing tests**
  Add test setups and assertions to reproduce config existence errors, missing source workspace errors, missing API key errors, and upfront case workspace collision errors.
  
  Replace the end of `test_agent_benchmark.py` (lines 73-108) with the following content:
  ```python
      (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")
      result = run_homllm_agent_benchmark(
          config_path=tmp_path / "config.yaml",
          source_workspace_root=source_workspace,
          workspace_root=tmp_path / "work",
          artifact_root=tmp_path / "runs",
          run_id="bench",
          case_ids=(
              INTERNAL_AGENT_BENCHMARK_CASES[0].case_id,
              INTERNAL_AGENT_BENCHMARK_CASES[1].case_id,
          ),
          live_api_key="test-key",
          agent_runner=fake_agent_runner,
      )
  
      assert result.run_id == "bench"
      assert result.total_cases == 2
      assert result.passed_cases == 2
      assert result.failed_cases == 0
      assert len(seen_requests) == 2
      assert seen_requests[0].run_id == f"bench-{INTERNAL_AGENT_BENCHMARK_CASES[0].case_id}"
      assert seen_requests[0].workspace_root == tmp_path / "work" / "bench" / "cases" / INTERNAL_AGENT_BENCHMARK_CASES[0].case_id
      summary = result.summary_metrics
      assert summary["stop_reason_counts"] == {"verified": 2}
      assert summary["numeric_metric_totals"]["patch_attempt_count"] == 2.0
      assert summary["numeric_metric_totals"]["verification_count"] == 2.0
      assert summary["numeric_metric_totals"]["provider_tokens_in"] == 20.0
      assert summary["numeric_metric_totals"]["provider_tokens_out"] == 14.0
      assert summary["numeric_metric_totals"]["index_source_file_count"] == 8.0
      assert summary["categorical_metric_counts"]["trajectory_verification_status"] == {"passed": 2}
      assert (
          tmp_path / "runs" / "bench" / "evaluation" / "summary.json"
      ).is_file()
  
  
  def test_run_homllm_agent_benchmark_checks_config_existence(tmp_path: Path) -> None:
      import pytest
      source_workspace = tmp_path / "source"
      source_workspace.mkdir()
  
      with pytest.raises(ValueError, match="config_not_found"):
          run_homllm_agent_benchmark(
              config_path=tmp_path / "config.yaml",
              source_workspace_root=source_workspace,
              workspace_root=tmp_path / "work",
              artifact_root=tmp_path / "runs",
              run_id="bench",
          )
  
  
  def test_run_homllm_agent_benchmark_checks_source_workspace_existence(tmp_path: Path) -> None:
      import pytest
      (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")
  
      with pytest.raises(ValueError, match="source_workspace_root_not_found"):
          run_homllm_agent_benchmark(
              config_path=tmp_path / "config.yaml",
              source_workspace_root=tmp_path / "nonexistent_source",
              workspace_root=tmp_path / "work",
              artifact_root=tmp_path / "runs",
              run_id="bench",
          )
  
  
  def test_run_homllm_agent_benchmark_checks_live_api_key_presence(tmp_path: Path) -> None:
      import pytest
      (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")
      source_workspace = tmp_path / "source"
      source_workspace.mkdir()
  
      with pytest.raises(ValueError, match="live_api_key_required"):
          run_homllm_agent_benchmark(
              config_path=tmp_path / "config.yaml",
              source_workspace_root=source_workspace,
              workspace_root=tmp_path / "work",
              artifact_root=tmp_path / "runs",
              run_id="bench",
              answer_provider_mode="live",
              live_api_key=None,
          )
  
  
  def test_run_homllm_agent_benchmark_checks_case_workspace_exists_upfront(tmp_path: Path) -> None:
      import pytest
      (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")
      source_workspace = tmp_path / "source"
      source_workspace.mkdir()
  
      case_workspace = tmp_path / "work" / "bench" / "cases" / INTERNAL_AGENT_BENCHMARK_CASES[0].case_id
      case_workspace.mkdir(parents=True)
  
      with pytest.raises(ValueError, match="case_workspace_exists"):
          run_homllm_agent_benchmark(
              config_path=tmp_path / "config.yaml",
              source_workspace_root=source_workspace,
              workspace_root=tmp_path / "work",
              artifact_root=tmp_path / "runs",
              run_id="bench",
              case_ids=(INTERNAL_AGENT_BENCHMARK_CASES[0].case_id,),
          )
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_agent_benchmark.py -v`
  Expected: Existing test passes, new checks tests fail with `AssertionError: Failed: DID NOT RAISE <class 'ValueError'>`.

- [ ] **Step 3: Commit**
  ```bash
  git add tests/unit/v4/test_agent_benchmark.py
  git commit -m "test: add regression tests for benchmark preflight validation checks"
  ```

---

### Task 2: Implement Preflight Validation Checks

**Files:**
- Modify: [agent_benchmark.py](file:///E:/HOM-LLM(v3.0)/src/homllm_v4/evaluation/agent_benchmark.py)

- [ ] **Step 1: Write minimal implementation**
  Add validation checks at the start of `run_homllm_agent_benchmark` in `src/homllm_v4/evaluation/agent_benchmark.py`:
  
  Replace the start of `run_homllm_agent_benchmark` (lines 181-204) with:
  ```python
  def run_homllm_agent_benchmark(
      *,
      config_path: Path,
      source_workspace_root: Path,
      workspace_root: Path,
      artifact_root: Path,
      run_id: str | None = None,
      case_ids: tuple[str, ...] | None = None,
      answer_provider_mode: str = "summary",
      live_provider_name: str = "gemini",
      live_model: str = "gemini-3.1-flash-lite-preview",
      live_api_key: str | None = None,
      live_max_output_tokens: int = 8192,
      max_prompt_chars: int | None = 22000,
      provider_repair_attempts: int = 1,
      smoke_safe: bool = True,
      index_skip_vectors: bool = False,
      agent_runner=run_homllm_agent,
  ) -> EvaluationRunResult:
      config_path = Path(config_path)
      if not config_path.exists():
          raise ValueError(f"config_not_found: {config_path}")
  
      source_workspace_root = Path(source_workspace_root).resolve()
      if not source_workspace_root.exists():
          raise ValueError(f"source_workspace_root_not_found: {source_workspace_root}")
  
      if answer_provider_mode == "live" and not live_api_key:
          raise ValueError("live_api_key_required")
  
      resolved_run_id = run_id or str(uuid4())
      workspace_root = Path(workspace_root).resolve()
      artifact_root = Path(artifact_root).resolve()
      cases = _select_cases(case_ids)
  
      for case in cases:
          target = workspace_root / resolved_run_id / "cases" / case.case_id
          if target.exists():
              raise ValueError(f"case_workspace_exists: {target}")
  ```

- [ ] **Step 2: Run test to verify it passes**
  Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_agent_benchmark.py -v`
  Expected: ALL PASS.

- [ ] **Step 3: Run the full v4 test suite to verify no regressions**
  Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/v4 -v`
  Expected: ALL PASS (218 passed).

- [ ] **Step 4: Commit**
  ```bash
  git add src/homllm_v4/evaluation/agent_benchmark.py
  git commit -m "feat: implement benchmark preflight validation checks in run_homllm_agent_benchmark"
  ```
