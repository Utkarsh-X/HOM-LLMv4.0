import json
import sys
from pathlib import Path

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.command import CommandRunResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.evaluation.agent_benchmark import (
    AgentBenchmarkCase,
    INTERNAL_AGENT_BENCHMARK_CASES,
    _case_requires_baseline_failure,
    run_homllm_agent_benchmark,
)
from homllm_v4.runtime.agent_run import HomllmAgentRunResult


class FakeBaselineService:
    """Returns a configured exit code for the first argv marker match."""

    def __init__(
        self,
        *,
        exit_codes: dict[str, int],
        timed_out: bool = False,
        denied: bool = False,
    ) -> None:
        self.exit_codes = exit_codes
        self.timed_out = timed_out
        self.denied = denied
        self.requests: list = []

    def run(self, request):
        self.requests.append(request)
        if self.denied:
            return CapabilityResult(
                capability_name="command.run",
                ok=False,
                output=None,
                error=CapabilityError(
                    code="command_denied",
                    message="denied",
                    recoverable=True,
                    retryable=False,
                ),
                telemetry=_empty_telemetry(),
                artifacts=(),
            )
        argv_text = " ".join(request.argv)
        exit_code = None
        for marker, code in self.exit_codes.items():
            if marker in argv_text:
                exit_code = code
                break
        if self.timed_out:
            exit_code = None
        output = CommandRunResult(
            argv=tuple(request.argv),
            cwd=request.cwd,
            exit_code=exit_code,
            stdout="",
            stderr="",
            duration_ms=3,
            timed_out=self.timed_out,
            denied=False,
        )
        return CapabilityResult(
            capability_name="command.run",
            ok=True,
            output=output,
            error=None,
            telemetry=_empty_telemetry(),
            artifacts=(),
        )


def _empty_telemetry() -> CapabilityTelemetry:
    return CapabilityTelemetry(
        started_at="",
        ended_at="",
        duration_ms=0,
        input_summary={},
        output_summary={},
        token_usage={},
        model_usage={},
        degraded=False,
        degradation_reason=None,
    )


def test_internal_agent_benchmark_suite_has_mvp_case_count() -> None:
    assert 10 <= len(INTERNAL_AGENT_BENCHMARK_CASES) <= 20
    case_ids = {case.case_id for case in INTERNAL_AGENT_BENCHMARK_CASES}
    assert len(case_ids) == len(INTERNAL_AGENT_BENCHMARK_CASES)
    for case in INTERNAL_AGENT_BENCHMARK_CASES:
        assert case.query
        assert case.expected_stop_reason == "verified"
        assert case.verification_argv


def test_internal_agent_benchmark_has_swebench_style_hidden_test_cases() -> None:
    """SWE-bench-style cases verify via pytest against hidden test files.

    The verification argv must invoke pytest on a tests/ module the agent
    never sees (index ignore_patterns exclude tests/**), and the canned
    provider mode must be a real behavior fix rather than a no-op.
    """
    hidden_cases = [
        case
        for case in INTERNAL_AGENT_BENCHMARK_CASES
        if (case.metadata or {}).get("verification_kind") == "hidden_test"
    ]
    assert len(hidden_cases) >= 5
    for case in hidden_cases:
        metadata = case.metadata or {}
        # Verification must be pytest, not an inline -c snippet: the test
        # contents stay hidden from the agent while the command stays runnable.
        assert "-m" in case.verification_argv
        assert "pytest" in case.verification_argv
        assert any(str(arg).endswith(".py") for arg in case.verification_argv)
        # Real bug fix, never a no-op provider mode.
        assert metadata.get("provider_mode") not in (None, "noop")
        # Localization is exercised when the target is omitted; at minimum the
        # cases must name a concrete target file the fix lands in.
        assert case.target_file is not None


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
                        "planner": {
                            "provider_tokens_in": 7,
                            "provider_tokens_out": 5,
                            "target_evidence_retrieved": True,
                            "retrieved_evidence_count": 3,
                            "target_file_retrieval_score": 0.9,
                            "current_content_truncated": False,
                        },
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
    assert summary["numeric_metric_totals"]["retrieved_evidence_count"] == 6.0
    assert summary["numeric_metric_totals"]["target_file_retrieval_score"] == 1.8
    assert summary["categorical_metric_counts"]["trajectory_verification_status"] == {"passed": 2}
    assert summary["categorical_metric_counts"]["target_evidence_retrieved"] == {"True": 2}
    assert result.case_results[0].metrics["retrieved_evidence_count"] == 3
    assert result.case_results[0].metrics["target_evidence_retrieved"] is True
    assert (
        tmp_path / "runs" / "bench" / "evaluation" / "summary.json"
    ).is_file()


def test_run_homllm_agent_benchmark_rejects_verified_run_with_empty_grounded_evidence(
    tmp_path: Path,
) -> None:
    source_workspace = tmp_path / "source"
    source_workspace.mkdir()
    (source_workspace / "module.py").write_text("VALUE = 1\n", encoding="utf-8")

    def fake_agent_runner(request):
        run_dir = Path(request.artifact_root) / request.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        session_path = run_dir / "session.json"
        trajectory_path = run_dir / "trajectory.json"
        session_path.write_text('{"session_id":"fake"}\n', encoding="utf-8")
        trajectory_path.write_text(
            json.dumps(
                {
                    "run_id": request.run_id,
                    "steps": [
                        {"name": "repo_index", "status": "built"},
                        {"name": "grounded_answer", "status": "empty_evidence"},
                        {"name": "bounded_edit", "status": "verified"},
                        {"name": "verification", "status": "passed"},
                    ],
                    "metrics": {"index": {"source_file_count": 1}},
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
            ask_stop_reason="empty_evidence",
            edit_stop_reason="verified",
            patch_attempt_count=1,
            provider_repair_attempt_count=0,
            verification_count=1,
            index_built=True,
            index_config_path=None,
            index_artifact_paths=None,
            index_metrics={"source_file_count": 1},
        )

    (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")
    result = run_homllm_agent_benchmark(
        config_path=tmp_path / "config.yaml",
        source_workspace_root=source_workspace,
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="bench-empty-grounding",
        case_ids=(INTERNAL_AGENT_BENCHMARK_CASES[0].case_id,),
        live_api_key="test-key",
        agent_runner=fake_agent_runner,
    )

    assert result.passed_cases == 0
    assert result.failed_cases == 1
    assert result.case_results[0].error_code == "benchmark_quality_gate_failed"
    assert result.case_results[0].metrics["benchmark_quality_failures"] == (
        "grounded_answer_not_sufficient",
    )


def test_run_homllm_agent_benchmark_passes_verified_run_with_bounded_ask_completion(
    tmp_path: Path,
) -> None:
    """A verified edit must not fail the gate when the read-only ask step
    completed in a bounded, evidence-backed state (budget_exhausted) instead of
    reaching the sufficiency threshold. Only ungrounded/failed ask steps
    (empty_evidence/service_failed) reject the case.
    """
    source_workspace = tmp_path / "source"
    source_workspace.mkdir()
    (source_workspace / "module.py").write_text("VALUE = 1\n", encoding="utf-8")

    def fake_agent_runner(request):
        run_dir = Path(request.artifact_root) / request.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        session_path = run_dir / "session.json"
        trajectory_path = run_dir / "trajectory.json"
        session_path.write_text('{"session_id":"fake"}\n', encoding="utf-8")
        trajectory_path.write_text(
            json.dumps(
                {
                    "run_id": request.run_id,
                    "steps": [
                        {"name": "repo_index", "status": "built"},
                        {"name": "grounded_answer", "status": "budget_exhausted"},
                        {"name": "bounded_edit", "status": "verified"},
                        {"name": "verification", "status": "passed"},
                    ],
                    "metrics": {"index": {"source_file_count": 1}},
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
            ask_stop_reason="budget_exhausted",
            edit_stop_reason="verified",
            patch_attempt_count=1,
            provider_repair_attempt_count=0,
            verification_count=1,
            index_built=True,
            index_config_path=None,
            index_artifact_paths=None,
            index_metrics={"source_file_count": 1},
        )

    (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")
    result = run_homllm_agent_benchmark(
        config_path=tmp_path / "config.yaml",
        source_workspace_root=source_workspace,
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="bench-bounded-ask",
        case_ids=(INTERNAL_AGENT_BENCHMARK_CASES[0].case_id,),
        live_api_key="test-key",
        agent_runner=fake_agent_runner,
    )

    assert result.passed_cases == 1
    assert result.failed_cases == 0
    assert result.case_results[0].metrics["benchmark_quality_gate"] == "passed"
    assert result.case_results[0].metrics["benchmark_quality_failures"] == ()


def test_run_homllm_agent_benchmark_fake_provider_wires_canned_edit_without_live_key(
    tmp_path: Path,
) -> None:
    import json

    from homllm_v4.evaluation.agent_benchmark import run_homllm_agent_benchmark
    from homllm_v4.planning.provider_edit_proposer import (
        ProviderEditProposalRequest,
    )

    source_workspace = tmp_path / "source"
    source_workspace.mkdir()
    (source_workspace / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    class CapturingVerifiedRunner:
        def __call__(self, request):
            captured["request"] = request
            assert request.edit_provider_builder is not None
            assert request.edit_require_live_api_key is False
            provider = request.edit_provider_builder()
            proposal = provider.propose_edit(
                ProviderEditProposalRequest(
                    task_id="probe",
                    prompt=(
                        "Evidence IDs: probe:candidate:utils/string_tools.py\n"
                        "Target file: utils/string_tools.py\n"
                        "Current content:\n"
                        "def truncate_string(text, max_length, suffix='...'):\n"
                        "    if len(text) <= max_length:\n"
                        "        return text\n"
                        "    return text[:max_length - len(suffix)] + suffix\n"
                    ),
                )
            )
            parsed = json.loads(proposal.text)
            assert parsed["target_file"] == "utils/string_tools.py"
            assert "max_length <= len(suffix)" in parsed["new_content"]
            assert parsed["evidence_ids"] == ["probe:candidate:utils/string_tools.py"]

            run_dir = Path(request.artifact_root) / request.run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            session_path = run_dir / "session.json"
            trajectory_path = run_dir / "trajectory.json"
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
                            {"name": "rollback", "status": "not_required", "occurred": False},
                        ],
                        "metrics": {"index": {"source_file_count": 2}},
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
                provider_repair_attempt_count=0,
                verification_count=1,
                index_built=True,
                index_config_path=None,
                index_artifact_paths=None,
                index_metrics={"source_file_count": 2},
            )

    result = run_homllm_agent_benchmark(
        config_path=tmp_path / "config.yaml",
        source_workspace_root=source_workspace,
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="bench-fake-canned",
        case_ids=("string-truncate-guard",),
        edit_provider_mode="fake",
        answer_provider_mode="summary",
        live_api_key=None,
        agent_runner=CapturingVerifiedRunner(),
    )
    assert result.total_cases == 1
    assert result.passed_cases == 1
    assert captured["request"].live_api_key is None


def test_run_homllm_agent_benchmark_fake_provider_requires_no_live_key(
    tmp_path: Path,
) -> None:
    import pytest
    from homllm_v4.evaluation.agent_benchmark import run_homllm_agent_benchmark

    source_workspace = tmp_path / "source"
    source_workspace.mkdir()
    (source_workspace / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")

    result = run_homllm_agent_benchmark(
        config_path=tmp_path / "config.yaml",
        source_workspace_root=source_workspace,
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="bench-fake-no-key",
        case_ids=("admin-routes-compile",),
        edit_provider_mode="fake",
        live_api_key=None,
        agent_runner=_FakeVerifiedAgentRunner(),
    )
    assert result.total_cases == 1
    assert result.passed_cases == 1


def test_run_homllm_agent_benchmark_rejects_unsupported_edit_provider_mode(
    tmp_path: Path,
) -> None:
    import pytest
    from homllm_v4.evaluation.agent_benchmark import run_homllm_agent_benchmark

    source_workspace = tmp_path / "source"
    source_workspace.mkdir()
    (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported_edit_provider_mode"):
        run_homllm_agent_benchmark(
            config_path=tmp_path / "config.yaml",
            source_workspace_root=source_workspace,
            workspace_root=tmp_path / "work",
            artifact_root=tmp_path / "runs",
            run_id="bench-bad-mode",
            case_ids=("admin-routes-compile",),
            edit_provider_mode="nope",
        )


def test_run_homllm_agent_benchmark_requires_live_key_for_live_edit_mode(
    tmp_path: Path,
) -> None:
    import pytest
    from homllm_v4.evaluation.agent_benchmark import run_homllm_agent_benchmark

    source_workspace = tmp_path / "source"
    source_workspace.mkdir()
    (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="live_api_key_required"):
        run_homllm_agent_benchmark(
            config_path=tmp_path / "config.yaml",
            source_workspace_root=source_workspace,
            workspace_root=tmp_path / "work",
            artifact_root=tmp_path / "runs",
            run_id="bench-live-key",
            case_ids=("admin-routes-compile",),
            edit_provider_mode="live",
            live_api_key=None,
        )


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


def test_case_requires_baseline_failure_derivation() -> None:
    def case(kind: str, *, explicit: bool | None = None) -> AgentBenchmarkCase:
        return AgentBenchmarkCase(
            case_id="x",
            query="q",
            edit_intent="e",
            expected_behavior="b",
            target_file="m.py",
            verification_argv=(sys.executable, "-c", "pass"),
            requires_baseline_failure=explicit,
            metadata={"verification_kind": kind},
        )

    assert _case_requires_baseline_failure(case("behavior")) is True
    assert _case_requires_baseline_failure(case("hidden_test")) is True
    assert _case_requires_baseline_failure(case("compile")) is False
    assert _case_requires_baseline_failure(case("compile", explicit=True)) is True


def test_verify_baseline_skips_stale_fixture_without_calling_agent(
    tmp_path: Path,
) -> None:
    source_workspace = tmp_path / "source"
    source_workspace.mkdir()
    (source_workspace / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")
    called: list = []

    def unexpected_agent_runner(request):
        called.append(request)
        raise AssertionError("agent must not run on a stale fixture")

    service = FakeBaselineService(exit_codes={"pytest": 0})
    result = run_homllm_agent_benchmark(
        config_path=tmp_path / "config.yaml",
        source_workspace_root=source_workspace,
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="bench-stale",
        case_ids=("hashing-needs-rehash-hidden-test",),
        edit_provider_mode="fake",
        verify_baseline=True,
        baseline_command_service=service,
        agent_runner=unexpected_agent_runner,
    )

    assert called == []
    assert result.total_cases == 1
    assert result.failed_cases == 1
    assert result.case_results[0].error_code == "baseline_stale"
    assert result.case_results[0].metrics["baseline_status"] == "stale"
    assert len(service.requests) == 1
    assert result.summary_metrics["baseline_counts"] == {
        "checked": 1,
        "healthy": 0,
        "stale": 1,
        "error": 0,
    }


def test_verify_baseline_healthy_fixture_runs_agent_and_records_metrics(
    tmp_path: Path,
) -> None:
    source_workspace = tmp_path / "source"
    source_workspace.mkdir()
    (source_workspace / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")

    service = FakeBaselineService(exit_codes={"pytest": 1})
    result = run_homllm_agent_benchmark(
        config_path=tmp_path / "config.yaml",
        source_workspace_root=source_workspace,
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="bench-healthy",
        case_ids=("hashing-needs-rehash-hidden-test",),
        edit_provider_mode="fake",
        verify_baseline=True,
        baseline_command_service=service,
        agent_runner=_FakeVerifiedAgentRunner(),
    )

    assert result.passed_cases == 1
    assert result.case_results[0].metrics["baseline_status"] == "healthy"
    assert result.case_results[0].metrics["baseline_check_count"] == 1
    assert result.summary_metrics["baseline_counts"]["healthy"] == 1
    assert result.summary_metrics["baseline_counts"]["checked"] == 1


def test_verify_baseline_timeout_skips_case_as_error(tmp_path: Path) -> None:
    source_workspace = tmp_path / "source"
    source_workspace.mkdir()
    (source_workspace / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")

    service = FakeBaselineService(exit_codes={"pytest": 1}, timed_out=True)
    result = run_homllm_agent_benchmark(
        config_path=tmp_path / "config.yaml",
        source_workspace_root=source_workspace,
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="bench-timeout",
        case_ids=("hashing-needs-rehash-hidden-test",),
        edit_provider_mode="fake",
        verify_baseline=True,
        baseline_command_service=service,
        agent_runner=_FakeVerifiedAgentRunner(),
    )

    assert result.failed_cases == 1
    assert result.case_results[0].error_code == "baseline_error"
    assert result.summary_metrics["baseline_counts"]["error"] == 1


def test_verify_baseline_must_pass_check_flags_broken_regression_tests(
    tmp_path: Path,
) -> None:
    source_workspace = tmp_path / "source"
    source_workspace.mkdir()
    (source_workspace / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")
    pytest_argv = (sys.executable, "-m", "pytest", "test_x.py", "-q")
    p2p_argv = (sys.executable, "-m", "pytest", "test_p2p.py", "-q")
    case = AgentBenchmarkCase(
        case_id="p2p-broken",
        query="q",
        edit_intent="e",
        expected_behavior="b",
        target_file="module.py",
        verification_argv=pytest_argv,
        metadata={
            "verification_kind": "hidden_test",
            "baseline_must_fail_argv": pytest_argv,
            "baseline_must_pass_argv": p2p_argv,
        },
    )

    # FAIL_TO_PASS reproduces (exit 1) but PASS_TO_PASS already fails on the
    # pristine repo (exit 1) -- the regression set is broken, so skip the case.
    service = FakeBaselineService(exit_codes={"test_x.py": 1, "test_p2p.py": 1})
    result = run_homllm_agent_benchmark(
        config_path=tmp_path / "config.yaml",
        source_workspace_root=source_workspace,
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="bench-p2p",
        cases=(case,),
        edit_provider_mode="fake",
        verify_baseline=True,
        baseline_command_service=service,
        agent_runner=_FakeVerifiedAgentRunner(),
    )

    assert result.failed_cases == 1
    assert result.case_results[0].error_code == "baseline_stale"
    assert len(service.requests) == 2


def test_verify_baseline_compile_kind_runs_without_must_fail_check(
    tmp_path: Path,
) -> None:
    source_workspace = tmp_path / "source"
    source_workspace.mkdir()
    (source_workspace / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("{}", encoding="utf-8")

    service = FakeBaselineService(exit_codes={})
    result = run_homllm_agent_benchmark(
        config_path=tmp_path / "config.yaml",
        source_workspace_root=source_workspace,
        workspace_root=tmp_path / "work",
        artifact_root=tmp_path / "runs",
        run_id="bench-compile",
        case_ids=("admin-routes-compile",),
        edit_provider_mode="fake",
        verify_baseline=True,
        baseline_command_service=service,
        agent_runner=_FakeVerifiedAgentRunner(),
    )

    assert result.passed_cases == 1
    assert result.case_results[0].metrics["baseline_status"] == "healthy"
    assert result.case_results[0].metrics["baseline_check_count"] == 0
    assert service.requests == []


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
            edit_provider_mode="fake",
        )


class _FakeVerifiedAgentRunner:
    def __call__(self, request):
        run_dir = Path(request.artifact_root) / request.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        session_path = run_dir / "session.json"
        trajectory_path = run_dir / "trajectory.json"
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
                    "metrics": {"index": {"source_file_count": 1}},
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
            provider_repair_attempt_count=0,
            verification_count=1,
            index_built=True,
            index_config_path=None,
            index_artifact_paths=None,
            index_metrics={"source_file_count": 1},
        )
