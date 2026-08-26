import json
from dataclasses import dataclass, field
from pathlib import Path

from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import DirectReadRequest, DirectReadResult
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.tool_loop import AgentToolLoopRequest
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.planning.provider_edit_proposer import (
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
)
from homllm_v4.runtime.agent_tool_loop import BoundedAgentToolLoop
from homllm_v4.runtime.agent_tools import AgentToolExecutor

DIFF = (
    "--- a/src/a.py\n"
    "+++ b/src/a.py\n"
    "@@ -1,1 +1,2 @@\n"
    "-old\n"
    "+new\n"
    "+extra\n"
)


def _propose_action_json(target_file: str = "src/a.py") -> str:
    """Build a propose_patch action payload without hand-escaped quotes."""
    return json.dumps(
        {
            "action": "propose_patch",
            "target_file": target_file,
            "diff": DIFF.replace("a/src/a.py", "a/" + target_file)
            .replace("b/src/a.py", "b/" + target_file),
            "rationale": "fix",
            "evidence_ids": [],
        }
    )


@dataclass
class ScriptedProvider:
    responses: list[str]
    prompts: list[str] = field(default_factory=list)

    def propose_edit(self, request: ProviderEditProposalRequest) -> ProviderEditProposalResponse:
        self.prompts.append(request.prompt)
        return ProviderEditProposalResponse(
            text=self.responses.pop(0),
            tokens_in=100,
            tokens_out=20,
            model="scripted",
            metadata={"finish_reason": "stop"},
        )


@dataclass
class StubReadService:
    excerpt: str = "old\n"

    def read(self, request: DirectReadRequest) -> CapabilityResult[DirectReadResult]:
        output = DirectReadResult(
            file_path=request.file_path,
            content_excerpt=self.excerpt,
            line_start=None,
            line_end=None,
            content_hash=None,
            truncated=False,
            freshness="fresh",
        )
        return CapabilityResult(
            capability_name="file.read",
            ok=True,
            output=output,
            error=None,
            telemetry=None,
            artifacts=(),
        )


@dataclass
class FailingReadService:
    def read(self, request: DirectReadRequest) -> CapabilityResult[DirectReadResult]:
        return CapabilityResult(
            capability_name="file.read",
            ok=False,
            output=None,
            error=CapabilityError(code="path_denied", message="outside workspace"),
            telemetry=None,
            artifacts=(),
        )


def loop_request(**overrides) -> AgentToolLoopRequest:
    defaults = dict(
        task_id="task-1",
        query="q",
        intent="i",
        expected_behavior="e",
        verification_summary="pytest -q",
        allowed_file_paths=("src/a.py",),
    )
    defaults.update(overrides)
    return AgentToolLoopRequest(**defaults)


def make_loop(provider, read_service=None) -> BoundedAgentToolLoop:
    return BoundedAgentToolLoop(
        provider=provider,
        executor=AgentToolExecutor(
            retrieval_service=_null_retrieval_service(),
            direct_read_service=read_service or StubReadService(),
            index_id="idx",
        ),
    )


def _null_retrieval_service():
    class _Null:
        def retrieve(self, request):
            raise AssertionError("search_repo not expected")

    return _Null()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_happy_path_read_then_propose(tmp_path: Path) -> None:
    provider = ScriptedProvider(
        responses=[
            '{"action": "read_file", "file_path": "src/a.py"}',
            '{"action": "propose_patch", "target_file": "src/a.py", "diff": '
            '"' + DIFF.replace("\n", "\\n").replace('"', '\\"') + '", "rationale": "fix", "evidence_ids": []}',
        ]
    )
    loop = make_loop(provider)
    loop.event_writer = EventWriter(tmp_path / "events.jsonl")

    result = loop.run(loop_request())

    assert result.ok is True
    assert result.output.stop_reason == "proposal_received"
    assert result.output.proposal.target_file == "src/a.py"
    assert "--- a/src/a.py" in result.output.proposal.diff
    assert result.output.total_tokens_in == 200
    assert len(result.output.turns) == 2
    events = read_jsonl(tmp_path / "events.jsonl")
    assert [event["event_type"] for event in events] == ["tool_call", "tool_call", "loop_stopped"]


def test_turn_budget_exhaustion() -> None:
    provider = ScriptedProvider(
        responses=[
            '{"action": "search_repo", "query": "q0"}',
            '{"action": "search_repo", "query": "q1"}',
            '{"action": "search_repo", "query": "q2"}',
            '{"action": "search_repo", "query": "q3"}',
            '{"action": "search_repo", "query": "q4"}',
        ],
    )
    loop = make_loop(provider)

    result = loop.run(loop_request(max_turns=3))

    assert result.output.stop_reason == "turn_budget_exhausted"
    assert len(result.output.turns) == 3


def test_token_budget_exhaustion() -> None:
    provider = ScriptedProvider(responses=['{"action": "search_repo", "query": "q"}'])
    loop = make_loop(provider)

    result = loop.run(loop_request(max_turns=5, max_total_tokens_in=50))

    assert result.output.stop_reason == "token_budget_exhausted"
    assert result.output.total_tokens_in == 100


def test_repetition_guard_warns_then_stops() -> None:
    provider = ScriptedProvider(responses=['{"action": "search_repo", "query": "same"}'] * 4)
    loop = make_loop(provider)

    result = loop.run(loop_request())

    assert result.output.stop_reason == "repeated_state"
    assert result.output.repeated_action_count >= 1
    assert result.output.turns[1].repeated_warning is True


def test_finish_without_patch_maps_to_retryable_failure() -> None:
    provider = ScriptedProvider(responses=['{"action": "finish", "rationale": "cannot fix safely"}'])
    loop = make_loop(provider)

    result = loop.run(loop_request())

    assert result.output.stop_reason == "finished_without_patch"
    assert result.output.error_code == "agent_finished_without_patch"
    assert result.output.proposal is None


def test_invalid_json_recovers_next_turn() -> None:
    provider = ScriptedProvider(
        responses=[
            "I will look around first.",
            '{"action": "propose_patch", "target_file": "src/a.py", "diff": '
            '"' + DIFF.replace("\n", "\\n").replace('"', '\\"') + '"}',
        ]
    )
    loop = make_loop(provider)

    result = loop.run(loop_request())

    assert result.output.stop_reason == "proposal_received"
    assert result.output.turns[0].action_name == "<invalid>"
    assert result.output.turns[0].observation_error_code == "provider_response_invalid"


def test_propose_outside_allowed_files_is_denied_and_loop_continues() -> None:
    denied_diff = DIFF.replace("src/a.py", "other/b.py")
    provider = ScriptedProvider(
        responses=[
            '{"action": "propose_patch", "target_file": "other/b.py", "diff": '
            '"' + denied_diff.replace("\n", "\\n").replace('"', '\\"') + '"}',
            '{"action": "propose_patch", "target_file": "src/a.py", "diff": '
            '"' + DIFF.replace("\n", "\\n").replace('"', '\\"') + '"}',
        ]
    )
    loop = make_loop(provider)

    result = loop.run(loop_request())

    assert result.output.stop_reason == "proposal_received"
    assert result.output.turns[0].observation_error_code == "proposal_file_denied"
    assert result.output.proposal.target_file == "src/a.py"


def test_provider_exception_stops_with_provider_error() -> None:
    @dataclass
    class ExplodingProvider:
        calls: int = 0

        def propose_edit(self, request: ProviderEditProposalRequest) -> ProviderEditProposalResponse:
            self.calls += 1
            raise RuntimeError("network down")

    provider = ExplodingProvider()
    loop = make_loop(provider)

    result = loop.run(loop_request())

    assert result.output.stop_reason == "provider_error"
    assert result.output.error_code == "provider_invocation_failed"
    assert provider.calls == 2


def test_prompt_carries_budget_and_near_budget_warning() -> None:
    propose = _propose_action_json()
    provider = ScriptedProvider(
        responses=[
            '{"action": "search_repo", "query": "q0"}',
            '{"action": "search_repo", "query": "q1"}',
            propose,
        ]
    )
    loop = make_loop(provider)

    result = loop.run(loop_request(max_turns=3))

    assert result.output.stop_reason == "proposal_received"
    assert "Turn budget: at most 3 actions in total" in provider.prompts[0]
    # prompts[1] carries the turn-0 observation block; prompts[2] the turn-1 one.
    assert "TURN 1/3" in provider.prompts[1]
    assert "BUDGET WARNING: only 2 action(s) remain" in provider.prompts[1]
    assert "TURN 2/3" in provider.prompts[2]
    assert "BUDGET WARNING: only 1 action(s) remain" in provider.prompts[2]


def test_invalid_response_emits_ledger_event(tmp_path: Path) -> None:
    provider = ScriptedProvider(
        responses=[
            "prose instead of json",
            _propose_action_json(),
        ]
    )
    loop = make_loop(provider)
    loop.event_writer = EventWriter(tmp_path / "events.jsonl")

    result = loop.run(loop_request())

    assert result.output.stop_reason == "proposal_received"
    events = read_jsonl(tmp_path / "events.jsonl")
    tool_calls = [event for event in events if event["event_type"] == "tool_call"]
    invalid_events = [
        event
        for event in tool_calls
        if event["summary"]["action"] == "<invalid>"
        and event["summary"]["error_code"] == "provider_response_invalid"
    ]
    assert len(invalid_events) == 1
    assert invalid_events[0]["summary"]["turn_index"] == 0


def test_invalid_response_archives_raw_text_and_finish_reason(tmp_path: Path) -> None:
    provider = ScriptedProvider(
        responses=[
            "prose instead of json",
            _propose_action_json(),
        ]
    )
    loop = make_loop(provider)
    loop.event_writer = EventWriter(tmp_path / "events.jsonl")

    result = loop.run(loop_request())

    assert result.output.stop_reason == "proposal_received"
    archived = tmp_path / "events.jsonl".replace("events.jsonl", "") / "agent_turns" / "turn_00.response.txt"
    assert archived.is_file()
    assert "prose instead of json" in archived.read_text(encoding="utf-8")

    events = read_jsonl(tmp_path / "events.jsonl")
    invalid_event = next(
        event
        for event in events
        if event["event_type"] == "tool_call" and event["summary"]["action"] == "<invalid>"
    )
    assert invalid_event["summary"]["finish_reason"] == "stop"
    assert "prose instead of json" in invalid_event["summary"]["response_excerpt"]
    valid_turns = [
        turn for turn in result.output.turns if turn.action_name != "<invalid>"
    ]
    assert all(turn.finish_reason is None for turn in valid_turns)
