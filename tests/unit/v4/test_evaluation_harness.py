import json
from pathlib import Path

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.evaluation import CaseExecutionResult, EvaluationCase
from homllm_v4.evaluation.harness import V4EvaluationHarness


def test_evaluation_harness_records_pass_fail_and_persists_summary(tmp_path: Path) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("eval-run-1", {})
    harness = V4EvaluationHarness(
        artifact_manager=manager,
        runners={
            "read_only": lambda case: CaseExecutionResult(
                stop_reason="sufficient",
                metrics={"pass_count": 1},
                error_code=None,
            ),
            "write_verify": lambda case: CaseExecutionResult(
                stop_reason="verification_failed",
                metrics={"patch_attempt_count": 1},
                error_code=None,
            ),
        },
    )

    result = harness.run(
        run_id="eval-run-1",
        cases=(
            EvaluationCase(
                case_id="ro-1",
                runner_id="read_only",
                task_type="read_only",
                input_payload={"query": "explain demo"},
                expected_stop_reason="sufficient",
            ),
            EvaluationCase(
                case_id="wv-1",
                runner_id="write_verify",
                task_type="write_verify",
                input_payload={"target": "demo.py"},
                expected_stop_reason="verified",
            ),
        ),
    )

    assert result.total_cases == 2
    assert result.passed_cases == 1
    assert result.failed_cases == 1
    assert result.case_results[0].passed is True
    assert result.case_results[1].passed is False
    artifact = tmp_path / ".homllm" / "runs" / "eval-run-1" / "evaluation" / "summary.json"
    assert artifact.is_file()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["passed_cases"] == 1
    assert payload["case_results"][1]["actual_stop_reason"] == "verification_failed"


def test_evaluation_harness_unknown_runner_fails_case_without_exception(tmp_path: Path) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("eval-run-1", {})
    harness = V4EvaluationHarness(artifact_manager=manager, runners={})

    result = harness.run(
        run_id="eval-run-1",
        cases=(
            EvaluationCase(
                case_id="missing-runner",
                runner_id="missing",
                task_type="read_only",
                input_payload={},
                expected_stop_reason="sufficient",
            ),
        ),
    )

    assert result.total_cases == 1
    assert result.failed_cases == 1
    assert result.case_results[0].passed is False
    assert result.case_results[0].error_code == "unknown_runner"


def test_evaluation_harness_records_runner_exception_diagnostics(tmp_path: Path) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("eval-run-1", {})

    def failing_runner(case):
        raise RuntimeError("transient provider failure")

    harness = V4EvaluationHarness(
        artifact_manager=manager,
        runners={"write_verify": failing_runner},
    )

    result = harness.run(
        run_id="eval-run-1",
        cases=(
            EvaluationCase(
                case_id="provider-down",
                runner_id="write_verify",
                task_type="python_patch",
                input_payload={},
                expected_stop_reason="verified",
            ),
        ),
    )

    case = result.case_results[0]
    assert case.error_code == "runner_exception:RuntimeError"
    assert case.metrics["runner_exception_type"] == "RuntimeError"
    assert case.metrics["runner_exception_message"] == "transient provider failure"
    assert result.summary_metrics["categorical_metric_counts"]["runner_exception_type"] == {
        "RuntimeError": 1
    }


def test_evaluation_harness_can_pass_expected_safety_error(tmp_path: Path) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("eval-run-1", {})
    harness = V4EvaluationHarness(
        artifact_manager=manager,
        runners={
            "write_verify": lambda case: CaseExecutionResult(
                stop_reason="patch_failed",
                metrics={},
                error_code="stale_context",
            ),
        },
    )

    result = harness.run(
        run_id="eval-run-1",
        cases=(
            EvaluationCase(
                case_id="stale-context",
                runner_id="write_verify",
                task_type="python_patch",
                input_payload={},
                expected_stop_reason="patch_failed",
                expected_error_code="stale_context",
            ),
        ),
    )

    assert result.total_cases == 1
    assert result.passed_cases == 1
    assert result.failed_cases == 0
    assert result.case_results[0].passed is True
    assert result.case_results[0].error_code == "stale_context"


def test_evaluation_harness_records_run_level_metric_summary(tmp_path: Path) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("eval-run-1", {})
    harness = V4EvaluationHarness(
        artifact_manager=manager,
        runners={
            "write_verify": lambda case: CaseExecutionResult(
                stop_reason=str(case.input_payload["stop_reason"]),
                metrics={
                    "duration_ms": case.input_payload["duration_ms"],
                    "token_count": case.input_payload["token_count"],
                    "target_selection_decision": case.input_payload[
                        "target_selection_decision"
                    ],
                    "used_baseline": case.input_payload["used_baseline"],
                },
            ),
        },
    )

    result = harness.run(
        run_id="eval-run-1",
        cases=(
            EvaluationCase(
                case_id="fast",
                runner_id="write_verify",
                task_type="python_patch",
                input_payload={
                    "stop_reason": "verified",
                    "duration_ms": 10,
                    "token_count": 100,
                    "target_selection_decision": "selected",
                    "used_baseline": True,
                },
                expected_stop_reason="verified",
            ),
            EvaluationCase(
                case_id="blocked",
                runner_id="write_verify",
                task_type="python_patch",
                input_payload={
                    "stop_reason": "patch_failed",
                    "duration_ms": 30,
                    "token_count": 20,
                    "target_selection_decision": "supplied",
                    "used_baseline": False,
                },
                expected_stop_reason="patch_failed",
            ),
        ),
    )

    assert result.summary_metrics["stop_reason_counts"] == {"verified": 1, "patch_failed": 1}
    assert result.summary_metrics["error_code_counts"] == {}
    assert result.summary_metrics["numeric_metric_averages"]["duration_ms"] == 20.0
    assert result.summary_metrics["numeric_metric_totals"]["token_count"] == 120.0
    assert result.summary_metrics["categorical_metric_counts"] == {
        "target_selection_decision": {"selected": 1, "supplied": 1},
        "used_baseline": {"False": 1, "True": 1},
    }


def test_evaluation_harness_can_attach_baseline_runner_comparison(tmp_path: Path) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("eval-run-1", {})
    harness = V4EvaluationHarness(
        artifact_manager=manager,
        runners={
            "candidate": lambda case: CaseExecutionResult(
                stop_reason="verified",
                metrics={"duration_ms": 10, "token_count": 100},
            ),
            "baseline": lambda case: CaseExecutionResult(
                stop_reason="verified",
                metrics={"duration_ms": 25, "token_count": 250},
            ),
        },
    )

    result = harness.run(
        run_id="eval-run-1",
        cases=(
            EvaluationCase(
                case_id="with-baseline",
                runner_id="candidate",
                baseline_runner_id="baseline",
                task_type="python_patch",
                input_payload={},
                expected_stop_reason="verified",
            ),
        ),
    )

    case_result = result.case_results[0]
    assert case_result.baseline_runner_id == "baseline"
    assert case_result.baseline_stop_reason == "verified"
    assert case_result.baseline_metrics == {"duration_ms": 25, "token_count": 250}
    assert case_result.metric_deltas == {"duration_ms": -15.0, "token_count": -150.0}
    assert result.summary_metrics["baseline_case_count"] == 1
