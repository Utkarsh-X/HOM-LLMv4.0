import json
import subprocess
import sys
from pathlib import Path

from homllm_v4 import cli
from homllm_v4.api import run_read_only_query
from homllm_v4.contracts.evaluation import EvaluationRunResult
from homllm_v4.contracts.loop import ReadOnlyLoopResult, SufficiencyDecision
from homllm_v4.runtime.agent_run import HomllmAgentRunResult
from homllm_v4.runtime.agent_session import AgentSessionResult


class FakeComponents:
    def __init__(self, service_registry, index_artifact_paths):
        self.service_registry = service_registry
        self.index_artifact_paths = index_artifact_paths


class FakeReadOnlyLoop:
    last_request = None

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def run(self, request):
        self.__class__.last_request = request
        return ReadOnlyLoopResult(
            task_id=request.task_id,
            run_id=request.run_id,
            stop_reason="sufficient",
            pass_count=1,
            sufficiency=SufficiencyDecision(True, 1.0, (), 1, 1),
            passes=(),
            context_pack=None,
            response_text="Evidence-backed context is ready.",
            claim_support=(),
            error=None,
        )


def fake_builder(config_path: Path, *, smoke_safe: bool):
    return FakeComponents(service_registry=object(), index_artifact_paths={"duckdb": "idx.duckdb"})


def test_run_read_only_query_uses_component_builder_and_returns_result(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("homllm_v4.api.ReadOnlyMultipassLoop", FakeReadOnlyLoop)

    result = run_read_only_query(
        config_path=Path("config.yaml"),
        workspace_root=tmp_path,
        query="explain demo",
        run_id="run-1",
        artifact_root=tmp_path / ".homllm" / "runs",
        max_passes=2,
        smoke_safe=True,
        component_builder=fake_builder,
    )

    assert result.stop_reason == "sufficient"
    assert FakeReadOnlyLoop.last_request is not None
    assert FakeReadOnlyLoop.last_request.query == "explain demo"
    assert FakeReadOnlyLoop.last_request.max_passes == 2
    assert FakeReadOnlyLoop.last_request.index_artifact_paths == {"duckdb": "idx.duckdb"}


def test_cli_read_only_prints_json_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    def fake_run_read_only_query(**kwargs):
        return ReadOnlyLoopResult(
            task_id="task",
            run_id=kwargs["run_id"],
            stop_reason="sufficient",
            pass_count=1,
            sufficiency=SufficiencyDecision(True, 1.0, (), 1, 1),
            passes=(),
            context_pack=None,
            response_text="Evidence-backed context is ready.",
            claim_support=(),
            error=None,
        )

    monkeypatch.setattr(cli, "run_read_only_query", fake_run_read_only_query)

    code = cli.main(
        (
            "read-only",
            "--config",
            "config.yaml",
            "--workspace-root",
            str(tmp_path),
            "--query",
            "explain demo",
            "--run-id",
            "run-1",
            "--artifact-root",
            str(tmp_path / ".homllm" / "runs"),
            "--smoke-safe",
        )
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == "run-1"
    assert payload["stop_reason"] == "sufficient"
    assert payload["pass_count"] == 1
    assert payload["artifact_root"] == str(tmp_path / ".homllm" / "runs")
    assert payload["response_text"] == "Evidence-backed context is ready."


def test_cli_agent_session_prints_combined_json(tmp_path: Path, monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_run_agent_session(request):
        captured["request"] = request
        return AgentSessionResult(
            run_id=request.run_id,
            ask_run_id=f"{request.run_id}-ask",
            ask_stop_reason="sufficient",
            answer_text="normalize lives in sku.py",
            answer_provider_mode=request.answer_provider_mode,
            answer_error_code=None,
            answer_metrics={"provider_tokens_in": 10, "provider_tokens_out": 5},
            edit_run_id=f"{request.run_id}-edit",
            edit_stop_reason="verified",
            edit_error_code=None,
            artifact_root=str(request.artifact_root),
            patch_attempt_count=1,
            provider_repair_attempt_count=0,
            verification_count=1,
            planner_metrics={"resolved_target_file": "sku.py"},
            index_built=True,
            index_config_path=str(request.artifact_root / request.run_id / "index" / "generated_config.yaml"),
            index_artifact_paths={"artifacts": str(request.artifact_root / request.run_id / "index")},
            index_metrics={"source_file_count": 1},
        )

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(cli, "run_agent_session", fake_run_agent_session)

    code = cli.main(
        (
            "agent-session",
            "--config",
            "config.yaml",
            "--workspace-root",
            str(tmp_path),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--run-id",
            "session-cli",
            "--query",
            "Where is normalize?",
            "--edit-intent",
            "Strip whitespace before uppercasing.",
            "--expected-behavior",
            "normalize(' sku ') returns 'SKU'.",
            "--target-file",
            "sku.py",
            "--verification-cmd",
            f"{sys.executable} -m compileall -q sku.py",
            "--live-api-key-env",
            "GOOGLE_API_KEY",
            "--answer-provider-mode",
            "live",
            "--prepare-index",
            "--index-skip-vectors",
        )
    )

    assert code == 0
    request = captured["request"]
    assert request.run_id == "session-cli"
    assert request.query == "Where is normalize?"
    assert request.edit_intent == "Strip whitespace before uppercasing."
    assert request.live_model == "gemini-3.1-flash-lite-preview"
    assert request.live_api_key == "test-key"
    assert request.answer_provider_mode == "live"
    assert request.prepare_index is True
    assert request.index_skip_vectors is True
    assert request.verification_argv[-3:] == ("compileall", "-q", "sku.py")
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "agent-session"
    assert payload["run_id"] == "session-cli"
    assert payload["ask_stop_reason"] == "sufficient"
    assert payload["edit_stop_reason"] == "verified"
    assert payload["index_built"] is True
    assert payload["answer_text"] == "normalize lives in sku.py"
    assert payload["answer_provider_mode"] == "live"
    assert payload["answer_error_code"] is None
    assert payload["answer_metrics"]["provider_tokens_in"] == 10


def test_cli_homllm_agent_run_prints_json_summary(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    captured: dict[str, object] = {}

    def fake_run_homllm_agent(request):
        captured["request"] = request
        return HomllmAgentRunResult(
            run_id=request.run_id,
            stop_reason="verified",
            error_code=None,
            session_state_path=str(request.artifact_root / request.run_id / "session.json"),
            trajectory_path=str(request.artifact_root / request.run_id / "trajectory.json"),
            artifact_root=str(request.artifact_root),
            answer_text="normalize lives in sku.py",
            answer_provider_mode=request.answer_provider_mode,
            ask_stop_reason="sufficient",
            edit_stop_reason="verified",
            patch_attempt_count=1,
            provider_repair_attempt_count=0,
            verification_count=1,
            index_built=True,
            index_config_path=str(request.artifact_root / request.run_id / "index" / "generated_config.yaml"),
            index_artifact_paths={"artifacts": str(request.artifact_root / request.run_id / "index")},
            index_metrics={"source_file_count": 1},
        )

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(cli, "run_homllm_agent", fake_run_homllm_agent)

    code = cli.main(
        (
            "homllm-agent",
            "run",
            "--config",
            "config.yaml",
            "--workspace-root",
            str(tmp_path),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--run-id",
            "agent-cli",
            "--query",
            "Where is normalize?",
            "--edit-intent",
            "Strip whitespace before uppercasing.",
            "--expected-behavior",
            "normalize(' sku ') returns 'SKU'.",
            "--target-file",
            "sku.py",
            "--verification-cmd",
            f"{sys.executable} -m compileall -q sku.py",
            "--live-api-key-env",
            "GOOGLE_API_KEY",
            "--answer-provider-mode",
            "live",
            "--prepare-index",
            "--index-skip-vectors",
        )
    )

    assert code == 0
    request = captured["request"]
    assert request.run_id == "agent-cli"
    assert request.query == "Where is normalize?"
    assert request.edit_intent == "Strip whitespace before uppercasing."
    assert request.live_api_key == "test-key"
    assert request.answer_provider_mode == "live"
    assert request.prepare_index is True
    assert request.index_skip_vectors is True
    assert request.verification_argv[-3:] == ("compileall", "-q", "sku.py")
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "homllm-agent run"
    assert payload["run_id"] == "agent-cli"
    assert payload["stop_reason"] == "verified"
    assert payload["session_state_path"] == str(tmp_path / "runs" / "agent-cli" / "session.json")
    assert payload["trajectory_path"] == str(tmp_path / "runs" / "agent-cli" / "trajectory.json")
    assert payload["verification_count"] == 1


def test_runtime_v4_cli_bootstraps_src_layout_from_repo_root() -> None:
    repo_root = Path(__file__).resolve().parents[3]

    result = subprocess.run(
        [sys.executable, "runtime/v4_cli.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "read-only" in result.stdout


def test_cli_eval_fixture_patch_prints_json_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    def fake_run_python_patch_fixture_suite(**kwargs):
        return EvaluationRunResult(
            run_id=kwargs["run_id"],
            total_cases=4,
            passed_cases=4,
            failed_cases=0,
            case_results=(),
            summary_metrics={"stop_reason_counts": {"verified": 1}},
        )

    monkeypatch.setattr(cli, "run_python_patch_fixture_suite", fake_run_python_patch_fixture_suite)

    code = cli.main(
        (
            "eval-fixture-patch",
            "--fixture-root",
            "fixtures/v4/python_patch_repo",
            "--workspace-root",
            str(tmp_path / "work"),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--run-id",
            "fixture-suite",
        )
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == "fixture-suite"
    assert payload["total_cases"] == 4
    assert payload["passed_cases"] == 4
    assert payload["failed_cases"] == 0
    assert payload["artifact_root"] == str((tmp_path / "runs").resolve())


def test_cli_eval_homllm_agent_lists_cases(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "agent_benchmark_case_metadata",
        lambda: (
            {
                "case_id": "case-a",
                "query": "query a",
                "target_file": "a.py",
                "expected_stop_reason": "verified",
                "metadata": {"verification_kind": "compile"},
            },
        ),
    )

    code = cli.main(("eval-homllm-agent", "--list-cases"))

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "eval-homllm-agent"
    assert payload["case_count"] == 1
    assert payload["cases"][0]["case_id"] == "case-a"


def test_cli_eval_homllm_agent_runs_benchmark(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    captured: dict[str, object] = {}

    def fake_run_homllm_agent_benchmark(**kwargs):
        captured.update(kwargs)
        return EvaluationRunResult(
            run_id=kwargs["run_id"],
            total_cases=2,
            passed_cases=2,
            failed_cases=0,
            case_results=(),
            summary_metrics={
                "stop_reason_counts": {"verified": 2},
                "numeric_metric_totals": {"verification_count": 2.0},
            },
        )

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(
        cli,
        "run_homllm_agent_benchmark",
        fake_run_homllm_agent_benchmark,
    )

    code = cli.main(
        (
            "eval-homllm-agent",
            "--config",
            "config.yaml",
            "--source-workspace-root",
            str(tmp_path / "source"),
            "--workspace-root",
            str(tmp_path / "work"),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--run-id",
            "agent-bench",
            "--case-id",
            "case-a",
            "--case-id",
            "case-b",
            "--live-api-key-env",
            "GOOGLE_API_KEY",
            "--answer-provider-mode",
            "live",
            "--index-skip-vectors",
        )
    )

    assert code == 0
    assert captured["run_id"] == "agent-bench"
    assert captured["case_ids"] == ("case-a", "case-b")
    assert captured["live_api_key"] == "test-key"
    assert captured["answer_provider_mode"] == "live"
    assert captured["index_skip_vectors"] is True
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "eval-homllm-agent"
    assert payload["run_id"] == "agent-bench"
    assert payload["total_cases"] == 2
    assert payload["passed_cases"] == 2
    assert payload["failed_cases"] == 0
    assert payload["summary_metrics"]["stop_reason_counts"] == {"verified": 2}
