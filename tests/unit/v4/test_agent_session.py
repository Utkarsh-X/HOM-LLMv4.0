from pathlib import Path
import json

from homllm_v4.contracts.context import ContextBlock, ContextPack
from homllm_v4.contracts.loop import ReadOnlyLoopResult, SufficiencyDecision
from homllm_v4.runtime.agent_session import AgentSessionRequest, run_agent_session
from homllm_v4.runtime.agent_task import AgentTaskResult
from homllm_v4.runtime.grounded_answer import GroundedAnswerResult


def read_only_result(
    run_id: str,
    response_text: str = "Grounded answer.",
    context_pack: ContextPack | None = None,
) -> ReadOnlyLoopResult:
    return ReadOnlyLoopResult(
        task_id=f"{run_id}:task",
        run_id=run_id,
        stop_reason="sufficient",
        pass_count=1,
        sufficiency=SufficiencyDecision(True, 1.0, (), 1, 1),
        passes=(),
        context_pack=context_pack,
        response_text=response_text,
        claim_support=(),
        error=None,
    )


def answer_context_pack() -> ContextPack:
    return ContextPack(
        context_pack_id="ctx-1",
        purpose="answer",
        text="",
        blocks=(
            ContextBlock(
                block_id="block-1",
                candidate_id="ev-1",
                file_path="sku.py",
                span_start=1,
                span_end=2,
                text="def normalize(value):\n    return value.upper()",
                token_count=10,
                score=0.9,
                citation="sku.py:1-2",
            ),
        ),
        used_tokens=10,
        dropped_candidates=(),
        diagnostics={},
    )


def edit_result(run_id: str) -> AgentTaskResult:
    return AgentTaskResult(
        run_id=run_id,
        stop_reason="verified",
        error_code=None,
        artifact_root="runs",
        patch_attempt_count=1,
        provider_repair_attempt_count=0,
        verification_count=1,
        planner_metrics={"resolved_target_file": "sku.py"},
        index_built=True,
        index_config_path="runs/session/edit/index/generated_config.yaml",
        index_artifact_paths={"artifacts": "runs/session/edit/index"},
        index_metrics={"source_file_count": 1},
    )


def write_template_config(path: Path) -> None:
    path.write_text(
        """
indexer:
  storage:
    duckdb_path: old/metadata.duckdb
    tantivy_path: old/bm25.index
    lancedb_path: old/vectors.lance
    artifacts_path: old
  vector_indexing_enabled: true
retrieval: {}
ranking: {}
context: {}
generation: {}
evaluation: {}
""".strip(),
        encoding="utf-8",
    )


def test_run_agent_session_answers_without_edit(tmp_path: Path) -> None:
    calls: dict[str, object] = {}

    def fake_read_only(**kwargs):
        calls["read_only"] = kwargs
        return read_only_result(kwargs["run_id"])

    result = run_agent_session(
        AgentSessionRequest(
            config_path=Path("config.yaml"),
            workspace_root=tmp_path,
            artifact_root=tmp_path / "runs",
            run_id="session-1",
            query="Explain normalize.",
            answer_provider_mode="summary",
            persist_session_state=False,
            read_only_runner=fake_read_only,
        )
    )

    assert result.run_id == "session-1"
    assert result.ask_run_id == "session-1-ask"
    assert result.edit_run_id is None
    assert result.answer_text == "Grounded answer."
    assert result.ask_stop_reason == "sufficient"
    assert result.edit_stop_reason is None
    assert result.index_built is False
    assert calls["read_only"]["run_id"] == "session-1-ask"
    assert calls["read_only"]["query"] == "Explain normalize."
    assert calls["read_only"]["artifact_root"] == tmp_path / "runs"


def test_run_agent_session_prepares_index_before_answering(tmp_path: Path) -> None:
    calls: dict[str, object] = {}
    config_path = tmp_path / "config.yaml"
    write_template_config(config_path)

    def fake_index_builder(**kwargs):
        calls["index"] = kwargs
        return {"source_file_count": 2}

    def fake_read_only(**kwargs):
        calls["read_only"] = kwargs
        return read_only_result(kwargs["run_id"])

    result = run_agent_session(
        AgentSessionRequest(
            config_path=config_path,
            workspace_root=tmp_path,
            artifact_root=tmp_path / "runs",
            run_id="session-index",
            query="Explain normalize.",
            answer_provider_mode="summary",
            persist_session_state=False,
            prepare_index=True,
            index_skip_vectors=True,
            index_builder=fake_index_builder,
            read_only_runner=fake_read_only,
        )
    )

    generated_config = (
        tmp_path / "runs" / "session-index" / "index" / "generated_config.yaml"
    ).resolve()
    assert result.index_built is True
    assert result.index_config_path == str(generated_config)
    assert calls["index"]["config_path"] == generated_config
    assert calls["read_only"]["config_path"] == generated_config
    assert calls["read_only"]["run_id"] == "session-index-ask"


def test_run_agent_session_answers_then_runs_bounded_edit(tmp_path: Path) -> None:
    calls: dict[str, object] = {}
    config_path = tmp_path / "config.yaml"
    write_template_config(config_path)

    def fake_read_only(**kwargs):
        calls["read_only"] = kwargs
        return read_only_result(kwargs["run_id"], response_text="normalize is in sku.py")

    def fake_edit(request):
        calls["edit"] = request
        return edit_result(request.run_id)

    result = run_agent_session(
        AgentSessionRequest(
            config_path=config_path,
            workspace_root=tmp_path,
            artifact_root=tmp_path / "runs",
            run_id="session-2",
            query="Where is normalize?",
            answer_provider_mode="summary",
            persist_session_state=False,
            edit_intent="Strip whitespace before uppercasing.",
            expected_behavior="normalize(' sku ') returns 'SKU'.",
            target_file="sku.py",
            verification_argv=("python.exe", "-m", "compileall", "-q", "sku.py"),
            live_api_key="test-key",
            prepare_index=True,
            index_skip_vectors=True,
            index_builder=lambda **kwargs: {"source_file_count": 1},
            read_only_runner=fake_read_only,
            edit_runner=fake_edit,
        )
    )

    edit_request = calls["edit"]
    assert result.run_id == "session-2"
    assert result.ask_run_id == "session-2-ask"
    assert result.edit_run_id == "session-2-edit"
    assert result.answer_text == "normalize is in sku.py"
    assert result.edit_stop_reason == "verified"
    assert result.index_built is True
    generated_config = (
        tmp_path / "runs" / "session-2" / "index" / "generated_config.yaml"
    ).resolve()
    assert result.index_config_path == str(generated_config)
    assert calls["read_only"]["run_id"] == "session-2-ask"
    assert calls["read_only"]["config_path"] == generated_config
    assert edit_request.run_id == "session-2-edit"
    assert edit_request.config_path == generated_config
    assert edit_request.query == "Where is normalize?"
    assert edit_request.intent == "Strip whitespace before uppercasing."
    assert edit_request.expected_behavior == "normalize(' sku ') returns 'SKU'."
    assert edit_request.prepare_index is False
    assert edit_request.index_skip_vectors is True


def test_run_agent_session_synthesizes_grounded_answer_from_context(tmp_path: Path) -> None:
    calls: dict[str, object] = {}

    def fake_read_only(**kwargs):
        calls["read_only"] = kwargs
        return read_only_result(
            kwargs["run_id"],
            response_text="Evidence-backed context is ready.",
            context_pack=answer_context_pack(),
        )

    class FakeSynthesizer:
        def synthesize(self, request):
            calls["answer"] = request
            return GroundedAnswerResult(
                ok=True,
                answer_text="Grounded provider answer.",
                metrics={"provider_tokens_in": 50, "provider_tokens_out": 9},
            )

    result = run_agent_session(
        AgentSessionRequest(
            config_path=Path("config.yaml"),
            workspace_root=tmp_path,
            artifact_root=tmp_path / "runs",
            run_id="session-answer",
            query="Where is normalize?",
            answer_provider_mode="live",
            live_api_key="test-key",
            answer_synthesizer=FakeSynthesizer(),
            persist_session_state=False,
            read_only_runner=fake_read_only,
        )
    )

    assert result.answer_text == "Grounded provider answer."
    assert result.answer_provider_mode == "live"
    assert result.answer_error_code is None
    assert result.answer_metrics["provider_tokens_in"] == 50
    assert calls["answer"].task_id == "session-answer-ask"
    assert calls["answer"].query == "Where is normalize?"
    assert calls["answer"].context_pack == answer_context_pack()


def test_run_agent_session_preserves_summary_when_answer_synthesis_fails_and_edits(
    tmp_path: Path,
) -> None:
    calls: dict[str, object] = {}

    def fake_read_only(**kwargs):
        calls["read_only"] = kwargs
        return read_only_result(
            kwargs["run_id"],
            response_text="Evidence-backed context is ready.",
            context_pack=answer_context_pack(),
        )

    def fake_edit(request):
        calls["edit"] = request
        return edit_result(request.run_id)

    class FailingSynthesizer:
        def synthesize(self, request):
            calls["answer"] = request
            return GroundedAnswerResult(
                ok=False,
                answer_text="",
                error_code="answer_provider_invocation_failed",
                metrics={"prompt_char_count": 100},
            )

    result = run_agent_session(
        AgentSessionRequest(
            config_path=Path("config.yaml"),
            workspace_root=tmp_path,
            artifact_root=tmp_path / "runs",
            run_id="session-answer-fallback",
            query="Where is normalize?",
            answer_provider_mode="live",
            live_api_key="test-key",
            answer_synthesizer=FailingSynthesizer(),
            persist_session_state=False,
            edit_intent="Strip whitespace before uppercasing.",
            expected_behavior="normalize(' sku ') returns 'SKU'.",
            target_file="sku.py",
            verification_argv=("python.exe", "-m", "compileall", "-q", "sku.py"),
            read_only_runner=fake_read_only,
            edit_runner=fake_edit,
        )
    )

    assert result.answer_text == "Evidence-backed context is ready."
    assert result.answer_error_code == "answer_provider_invocation_failed"
    assert result.answer_metrics["prompt_char_count"] == 100
    assert result.edit_stop_reason == "verified"
    assert calls["edit"].run_id == "session-answer-fallback-edit"


def test_run_agent_session_persists_session_turn_state(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    write_template_config(config_path)

    def fake_read_only(**kwargs):
        return read_only_result(
            kwargs["run_id"],
            response_text="normalize is in sku.py",
        )

    def fake_edit(request):
        return edit_result(request.run_id)

    result = run_agent_session(
        AgentSessionRequest(
            config_path=config_path,
            workspace_root=tmp_path,
            artifact_root=tmp_path / "runs",
            run_id="session-state",
            query="Where is normalize?",
            answer_provider_mode="summary",
            edit_intent="Strip whitespace before uppercasing.",
            expected_behavior="normalize(' sku ') returns 'SKU'.",
            target_file="sku.py",
            verification_argv=("python.exe", "-m", "compileall", "-q", "sku.py"),
            live_api_key="test-key",
            prepare_index=True,
            index_skip_vectors=True,
            index_builder=lambda **kwargs: {"source_file_count": 1},
            read_only_runner=fake_read_only,
            edit_runner=fake_edit,
        )
    )

    session_path = tmp_path / "runs" / "session-state" / "session.json"
    payload = json.loads(session_path.read_text(encoding="utf-8"))
    assert payload["session_id"] == "session-state"
    assert payload["workspace_root"] == str(tmp_path.resolve())
    assert payload["config_path"] == result.index_config_path
    assert payload["instruction"] == "Where is normalize?"
    assert payload["index_built"] is True
    assert payload["index_config_path"] == result.index_config_path
    assert payload["index_metrics"] == {"source_file_count": 1}
    assert len(payload["turns"]) == 1
    turn = payload["turns"][0]
    assert turn["turn_index"] == 1
    assert turn["query"] == "Where is normalize?"
    assert turn["ask_run_id"] == "session-state-ask"
    assert turn["ask_stop_reason"] == "sufficient"
    assert turn["answer_text"] == "normalize is in sku.py"
    assert turn["answer_provider_mode"] == "summary"
    assert turn["edit_run_id"] == "session-state-edit"
    assert turn["edit_stop_reason"] == "verified"
    assert turn["metrics"]["patch_attempt_count"] == 1
    assert turn["metrics"]["verification_count"] == 1
    assert turn["metrics"]["resolved_target_file"] == "sku.py"


def test_run_agent_session_can_skip_session_state_persistence(tmp_path: Path) -> None:
    def fake_read_only(**kwargs):
        return read_only_result(kwargs["run_id"])

    run_agent_session(
        AgentSessionRequest(
            config_path=Path("config.yaml"),
            workspace_root=tmp_path,
            artifact_root=tmp_path / "runs",
            run_id="session-no-state",
            query="Explain normalize.",
            answer_provider_mode="summary",
            persist_session_state=False,
            read_only_runner=fake_read_only,
        )
    )

    assert not (tmp_path / "runs" / "session-no-state" / "session.json").exists()
