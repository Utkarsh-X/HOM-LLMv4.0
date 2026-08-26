import pytest

from homllm_v4.contracts.tool_loop import (
    AGENT_LOOP_STOP_REASONS,
    AgentLoopTurn,
    AgentProposal,
    AgentToolLoopRequest,
    AgentToolLoopResult,
    AgentToolObservation,
)


def test_agent_tool_loop_request_defaults() -> None:
    request = AgentToolLoopRequest(
        task_id="task-1",
        query="fix truncate",
        intent="fix",
        expected_behavior="returns prefix",
        verification_summary="pytest -q",
    )
    assert request.max_turns == 10
    assert request.proposal_mode == "unified_diff"
    assert request.seed_evidence == ()
    assert request.allowed_file_paths == ()
    assert request.max_total_tokens_in is None
    assert request.max_total_tokens_out is None
    assert request.repair_context == ""
    assert request.seed_target_file is None


def test_agent_tool_loop_request_is_frozen() -> None:
    request = AgentToolLoopRequest(
        task_id="task-1",
        query="q",
        intent="i",
        expected_behavior="e",
        verification_summary="v",
    )
    with pytest.raises(Exception):
        request.task_id = "other"


def test_stop_reasons_are_complete() -> None:
    assert set(AGENT_LOOP_STOP_REASONS) == {
        "proposal_received",
        "finished_without_patch",
        "turn_budget_exhausted",
        "token_budget_exhausted",
        "repeated_state",
        "provider_error",
    }


def test_result_defaults() -> None:
    turn = AgentLoopTurn(
        turn_index=0,
        action_name="read_file",
        arguments_summary={"file_path": "a.py"},
        observation_ok=True,
        observation_error_code=None,
        observation_chars=120,
        repeated_warning=False,
        prompt_chars=500,
        response_chars=80,
        tokens_in=10,
        tokens_out=4,
        model="fake-model",
    )
    result = AgentToolLoopResult(stop_reason="proposal_received", turns=(turn,))
    assert result.turns[0].action_name == "read_file"
    assert result.proposal is None
    assert result.total_tokens_in == 0
    assert result.total_tokens_out == 0
    assert result.repeated_action_count == 0


def test_observation_and_proposal_shapes() -> None:
    observation = AgentToolObservation(ok=False, content="", error_code="unknown_tool")
    assert observation.truncated is False
    proposal = AgentProposal(target_file="a.py", diff="--- a\n+++ b\n", rationale="r")
    assert proposal.evidence_ids == ()
    assert proposal.risk_flags == ()
