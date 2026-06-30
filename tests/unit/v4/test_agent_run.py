import json
from pathlib import Path

from homllm_v4.runtime.agent_run import HomllmAgentRunRequest, run_homllm_agent
from homllm_v4.runtime.agent_session import AgentSessionResult


def test_run_homllm_agent_writes_trajectory_and_session_state_path(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_session_runner(request):
        captured["request"] = request
        session_dir = Path(request.artifact_root) / request.run_id
        session_dir.mkdir(parents=True)
        (session_dir / "session.json").write_text('{"session_id":"agent-run"}\n', encoding="utf-8")
        return AgentSessionResult(
            run_id=request.run_id,
            ask_run_id=f"{request.run_id}-ask",
            ask_stop_reason="sufficient",
            answer_text="normalize is implemented in sku.py",
            answer_provider_mode=request.answer_provider_mode,
            answer_error_code=None,
            answer_metrics={"provider_tokens_in": 10},
            edit_run_id=f"{request.run_id}-edit",
            edit_stop_reason="verified",
            edit_error_code=None,
            artifact_root=str(request.artifact_root),
            patch_attempt_count=1,
            provider_repair_attempt_count=0,
            verification_count=1,
            planner_metrics={"resolved_target_file": "sku.py"},
            index_built=True,
            index_config_path=str(Path(request.artifact_root) / request.run_id / "index" / "generated_config.yaml"),
            index_artifact_paths={"artifacts": str(Path(request.artifact_root) / request.run_id / "index")},
            index_metrics={"source_file_count": 1},
        )

    result = run_homllm_agent(
        HomllmAgentRunRequest(
            config_path=tmp_path / "config.yaml",
            workspace_root=tmp_path / "repo",
            artifact_root=tmp_path / "runs",
            run_id="agent-run",
            query="Where is normalize?",
            answer_provider_mode="live",
            edit_intent="Strip whitespace before uppercasing.",
            expected_behavior="normalize(' sku ') returns 'SKU'.",
            target_file="sku.py",
            verification_argv=("python.exe", "-m", "compileall", "-q", "sku.py"),
            live_api_key="test-key",
            prepare_index=True,
            session_runner=fake_session_runner,
        )
    )

    assert result.run_id == "agent-run"
    assert result.stop_reason == "verified"
    assert result.session_state_path == str(tmp_path / "runs" / "agent-run" / "session.json")
    assert result.trajectory_path == str(tmp_path / "runs" / "agent-run" / "trajectory.json")
    assert captured["request"].persist_session_state is True
    payload = json.loads(Path(result.trajectory_path).read_text(encoding="utf-8"))
    assert payload["run_id"] == "agent-run"
    assert payload["session_state_path"] == result.session_state_path
    assert payload["steps"] == [
        {"name": "repo_index", "status": "built", "config_path": result.index_config_path},
        {"name": "grounded_answer", "status": "sufficient", "provider_mode": "live"},
        {"name": "bounded_edit", "status": "verified", "patch_attempt_count": 1},
        {"name": "verification", "status": "passed", "verification_count": 1},
    ]


def test_run_homllm_agent_ignores_answer_error_code_when_edit_succeeds(tmp_path: Path) -> None:
    def fake_session_runner(request):
        session_dir = Path(request.artifact_root) / request.run_id
        session_dir.mkdir(parents=True)
        (session_dir / "session.json").write_text('{"session_id":"agent-run"}\n', encoding="utf-8")
        return AgentSessionResult(
            run_id=request.run_id,
            ask_run_id=f"{request.run_id}-ask",
            ask_stop_reason="empty_evidence",
            answer_text="",
            answer_provider_mode=request.answer_provider_mode,
            answer_error_code="answer_context_missing",
            answer_metrics={"provider_tokens_in": 0},
            edit_run_id=f"{request.run_id}-edit",
            edit_stop_reason="verified",
            edit_error_code=None,
            artifact_root=str(request.artifact_root),
            patch_attempt_count=1,
            provider_repair_attempt_count=0,
            verification_count=1,
            planner_metrics={"resolved_target_file": "sku.py"},
            index_built=True,
            index_config_path=str(Path(request.artifact_root) / request.run_id / "index" / "generated_config.yaml"),
            index_artifact_paths={"artifacts": str(Path(request.artifact_root) / request.run_id / "index")},
            index_metrics={"source_file_count": 1},
        )

    result = run_homllm_agent(
        HomllmAgentRunRequest(
            config_path=tmp_path / "config.yaml",
            workspace_root=tmp_path / "repo",
            artifact_root=tmp_path / "runs",
            run_id="agent-run",
            query="Where is normalize?",
            answer_provider_mode="live",
            edit_intent="Strip whitespace before uppercasing.",
            expected_behavior="normalize(' sku ') returns 'SKU'.",
            target_file="sku.py",
            verification_argv=("python.exe", "-m", "compileall", "-q", "sku.py"),
            live_api_key="test-key",
            prepare_index=True,
            session_runner=fake_session_runner,
        )
    )

    assert result.stop_reason == "verified"
    assert result.error_code is None

