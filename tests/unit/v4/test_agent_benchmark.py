import json
from pathlib import Path

from homllm_v4.evaluation.agent_benchmark import (
    INTERNAL_AGENT_BENCHMARK_CASES,
    run_homllm_agent_benchmark,
)
from homllm_v4.runtime.agent_run import HomllmAgentRunResult


def test_internal_agent_benchmark_suite_has_mvp_case_count() -> None:
    assert 10 <= len(INTERNAL_AGENT_BENCHMARK_CASES) <= 20
    case_ids = {case.case_id for case in INTERNAL_AGENT_BENCHMARK_CASES}
    assert len(case_ids) == len(INTERNAL_AGENT_BENCHMARK_CASES)
    for case in INTERNAL_AGENT_BENCHMARK_CASES:
        assert case.query
        assert case.expected_stop_reason == "verified"
        assert case.verification_argv


def test_run_homllm_agent_benchmark_aggregates_trajectory_metrics(
    tmp_path: Path,
) -> None:
    source_workspace = tmp_path / "source"
    source_workspace.mkdir()
    (source_workspace / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    seen_requests = []

    def fake_agent_runner(request):
        seen_requests.append(request)
        run_dir = Path(request.artifact_root) / request.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        trajectory_path = run_dir / "trajectory.json"
        session_path = run_dir / "session.json"
        session_path.write_text('{"session_id":"fake"}\n', encoding="utf-8")
        trajectory_path.write_text(
            json.dumps(
                {
                    "run_id": request.run_id,
                    "steps": [
                        {"name": "repo_index", "status": "built"},
                        {"name": "grounded_answer", "status": "sufficient"},
                        {"name": "bounded_edit", "status": "verified"},
                        {"name": "verification", "status": "passed"},
                    ],
                    "metrics": {
                        "answer": {"provider_tokens_in": 3, "provider_tokens_out": 2},
                        "planner": {"provider_tokens_in": 7, "provider_tokens_out": 5},
                        "index": {"source_file_count": 4},
                        "provider_repair_attempt_count": 1,
                    },
                }
            ),
            encoding="utf-8",
        )
        return HomllmAgentRunResult(
            run_id=request.run_id,
            stop_reason="verified",
            error_code=None,
            session_state_path=str(session_path),
            trajectory_path=str(trajectory_path),
            artifact_root=str(request.artifact_root),
            answer_text="ok",
            answer_provider_mode=request.answer_provider_mode,
            ask_stop_reason="sufficient",
            edit_stop_reason="verified",
            patch_attempt_count=1,
            provider_repair_attempt_count=1,
            verification_count=1,
            index_built=True,
            index_config_path=str(Path(request.artifact_root) / request.run_id / "index.yaml"),
            index_artifact_paths={"artifacts": str(Path(request.artifact_root) / request.run_id / "index")},
            index_metrics={"source_file_count": 4},
        )

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
