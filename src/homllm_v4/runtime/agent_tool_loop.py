"""Bounded, model-driven tool loop over the existing text provider seam.

Each turn the model returns exactly one JSON action object (see
``planning/agent_loop_prompts.py``); read/search actions execute through
:class:`~homllm_v4.runtime.agent_tools.AgentToolExecutor`, ``propose_patch``
terminates the loop with a validated :class:`AgentProposal`, and ``finish``
terminates with a structured no-patch failure. Turn count, cumulative token
usage, transcript growth, and repeated actions are all hard-bounded.
"""

import json
from dataclasses import replace
from time import perf_counter
from uuid import uuid4

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.contracts.tool_loop import (
    AgentLoopTurn,
    AgentProposal,
    AgentToolLoopRequest,
    AgentToolLoopResult,
    AgentToolObservation,
)
from homllm_v4.ledger.events import RunEvent
from homllm_v4.planning.agent_loop_prompts import (
    build_initial_prompt,
    parse_agent_action,
    render_observation_block,
)
from homllm_v4.planning.provider_edit_proposer import ProviderEditProposalRequest
from homllm_v4.runtime.agent_tools import AgentToolExecutor

_SENTINEL = "NEXT_ACTION:"
_TRANSCRIPT_OBS_CHARS = 4000


class BoundedAgentToolLoop:
    def __init__(
        self,
        *,
        provider: object,
        executor: AgentToolExecutor,
        event_writer: object | None = None,
        max_turns_default: int = 10,
        repetition_warn_threshold: int = 2,
        repetition_stop_threshold: int = 3,
    ) -> None:
        self.provider = provider
        self.executor = executor
        self.event_writer = event_writer
        self.max_turns_default = max(1, int(max_turns_default))
        self.repetition_warn_threshold = max(1, int(repetition_warn_threshold))
        self.repetition_stop_threshold = max(
            self.repetition_warn_threshold + 1, int(repetition_stop_threshold)
        )

    def run(self, request: AgentToolLoopRequest) -> CapabilityResult[AgentToolLoopResult]:
        started = perf_counter()
        initial = build_initial_prompt(request)
        header = initial[: -len(_SENTINEL)].rstrip() if initial.endswith(_SENTINEL) else initial
        max_turns = max(1, int(request.max_turns or self.max_turns_default))

        transcript: list[str] = []
        turns: list[AgentLoopTurn] = []
        seen_counts: dict[str, int] = {}
        total_in = 0
        total_out = 0
        tool_call_counts: dict[str, int] = {}
        repeated_total = 0

        for turn_index in range(max_turns):
            prompt = _compose_prompt(header, transcript)
            try:
                response = self.provider.propose_edit(
                    ProviderEditProposalRequest(task_id=request.task_id, prompt=prompt)
                )
            except Exception:
                try:
                    response = self.provider.propose_edit(
                        ProviderEditProposalRequest(task_id=request.task_id, prompt=prompt)
                    )
                except Exception as exc:
                    result = AgentToolLoopResult(
                        stop_reason="provider_error",
                        turns=tuple(turns),
                        error_code="provider_invocation_failed",
                        error_message=str(exc),
                        total_tokens_in=total_in,
                        total_tokens_out=total_out,
                        repeated_action_count=repeated_total,
                    )
                    self._emit_stop(request, result)
                    return _wrap(result, started)

            total_in += int(response.tokens_in)
            total_out += int(response.tokens_out)

            try:
                parsed = parse_agent_action(response.text)
            except ValueError as exc:
                detail = str(exc)
                meta = getattr(response, "metadata", {}) or {}
                finish_reason = str(meta.get("finish_reason") or "unknown")
                if finish_reason in ("length", "max_tokens"):
                    detail += (
                        " (response was cut off by the output-token limit; "
                        "reason less and emit the JSON action earlier)"
                    )
                else:
                    detail += (
                        " Return exactly ONE ```json fenced object with a single action."
                    )
                observation = AgentToolObservation(
                    ok=False, content=detail, error_code="provider_response_invalid"
                )
                self._archive_response(request, turn_index, response.text)
                turns.append(
                    AgentLoopTurn(
                        turn_index=turn_index,
                        action_name="<invalid>",
                        arguments_summary={},
                        observation_ok=False,
                        observation_error_code="provider_response_invalid",
                        observation_chars=len(observation.content),
                        repeated_warning=False,
                        prompt_chars=len(prompt),
                        response_chars=len(response.text),
                        tokens_in=int(response.tokens_in),
                        tokens_out=int(response.tokens_out),
                        model=str(getattr(response, "model", "unknown")),
                        finish_reason=finish_reason,
                        response_excerpt=response.text[:400],
                    )
                )
                transcript.append(
                    render_observation_block(
                        turn_index,
                        "<invalid>",
                        observation,
                        turns_total=max_turns,
                        turns_remaining=max_turns - turn_index - 1,
                    )
                )
                # Invalid responses consume a turn silently otherwise; surface
                # them in the ledger so parse-failure loops are diagnosable.
                self._emit_tool_call(request, turns[-1])
                continue

            action_name = parsed.name
            repeat_key = json.dumps([action_name, sorted(parsed.arguments.items(), key=lambda kv: kv[0])], default=str)
            seen_counts[repeat_key] = seen_counts.get(repeat_key, 0) + 1
            seen_count = seen_counts[repeat_key]
            warning = seen_count >= self.repetition_warn_threshold

            if seen_count >= self.repetition_stop_threshold:
                turn = AgentLoopTurn(
                    turn_index=turn_index,
                    action_name=action_name,
                    arguments_summary=_arguments_summary(parsed.arguments),
                    observation_ok=False,
                    observation_error_code="repeated_action",
                    observation_chars=0,
                    repeated_warning=True,
                    prompt_chars=len(prompt),
                    response_chars=len(response.text),
                    tokens_in=int(response.tokens_in),
                    tokens_out=int(response.tokens_out),
                    model=str(getattr(response, "model", "unknown")),
                )
                turns.append(turn)
                repeated_total += 1
                result = AgentToolLoopResult(
                    stop_reason="repeated_state",
                    turns=tuple(turns),
                    error_code="agent_repeated_state",
                    error_message=f"action repeated {seen_count} times",
                    total_tokens_in=total_in,
                    total_tokens_out=total_out,
                    repeated_action_count=repeated_total,
                )
                self._emit_tool_call(request, turn)
                self._emit_stop(request, result)
                return _wrap(result, started)

            if action_name == "propose_patch":
                proposal_observation = _validate_proposal(parsed.arguments, request.allowed_file_paths)
                if proposal_observation is not None:
                    observation = proposal_observation
                else:
                    proposal = AgentProposal(
                        target_file=str(parsed.arguments["target_file"]),
                        diff=str(parsed.arguments["diff"]),
                        rationale=str(parsed.arguments.get("rationale") or ""),
                        evidence_ids=_string_tuple(parsed.arguments.get("evidence_ids")),
                        risk_flags=_string_tuple(parsed.arguments.get("risk_flags")),
                    )
                    turn = AgentLoopTurn(
                        turn_index=turn_index,
                        action_name=action_name,
                        arguments_summary=_arguments_summary(parsed.arguments),
                        observation_ok=True,
                        observation_error_code=None,
                        observation_chars=0,
                        repeated_warning=False,
                        prompt_chars=len(prompt),
                        response_chars=len(response.text),
                        tokens_in=int(response.tokens_in),
                        tokens_out=int(response.tokens_out),
                        model=str(getattr(response, "model", "unknown")),
                    )
                    turns.append(turn)
                    tool_call_counts[action_name] = tool_call_counts.get(action_name, 0) + 1
                    result = AgentToolLoopResult(
                        stop_reason="proposal_received",
                        turns=tuple(turns),
                        proposal=proposal,
                        total_tokens_in=total_in,
                        total_tokens_out=total_out,
                        repeated_action_count=repeated_total,
                    )
                    self._emit_tool_call(request, turn)
                    self._emit_stop(request, result)
                    return _wrap(result, started)
            elif action_name == "finish":
                turn = AgentLoopTurn(
                    turn_index=turn_index,
                    action_name=action_name,
                    arguments_summary=_arguments_summary(parsed.arguments),
                    observation_ok=True,
                    observation_error_code=None,
                    observation_chars=0,
                    repeated_warning=False,
                    prompt_chars=len(prompt),
                    response_chars=len(response.text),
                    tokens_in=int(response.tokens_in),
                    tokens_out=int(response.tokens_out),
                    model=str(getattr(response, "model", "unknown")),
                )
                turns.append(turn)
                result = AgentToolLoopResult(
                    stop_reason="finished_without_patch",
                    turns=tuple(turns),
                    error_code="agent_finished_without_patch",
                    error_message=str(parsed.arguments.get("rationale") or "no patch proposed"),
                    total_tokens_in=total_in,
                    total_tokens_out=total_out,
                    repeated_action_count=repeated_total,
                )
                self._emit_tool_call(request, turn)
                self._emit_stop(request, result)
                return _wrap(result, started)
            else:
                observation = self.executor.execute(
                    task_id=request.task_id,
                    name=action_name,
                    arguments=parsed.arguments,
                )

            if warning:
                observation = replace(
                    observation,
                    content=(
                        "WARNING: you have repeated this exact action; change approach "
                        "or propose a patch.\n" + observation.content
                    ),
                )
            turn = AgentLoopTurn(
                turn_index=turn_index,
                action_name=action_name,
                arguments_summary=_arguments_summary(parsed.arguments),
                observation_ok=observation.ok,
                observation_error_code=observation.error_code,
                observation_chars=len(observation.content),
                repeated_warning=warning,
                prompt_chars=len(prompt),
                response_chars=len(response.text),
                tokens_in=int(response.tokens_in),
                tokens_out=int(response.tokens_out),
                model=str(getattr(response, "model", "unknown")),
            )
            turns.append(turn)
            tool_call_counts[action_name] = tool_call_counts.get(action_name, 0) + 1
            transcript.append(
                render_observation_block(
                    turn_index,
                    action_name,
                    observation,
                    turns_total=max_turns,
                    turns_remaining=max_turns - turn_index - 1,
                )[:_TRANSCRIPT_OBS_CHARS]
            )
            self._emit_tool_call(request, turn)

            if (
                request.max_total_tokens_in is not None and total_in > int(request.max_total_tokens_in)
            ) or (
                request.max_total_tokens_out is not None and total_out > int(request.max_total_tokens_out)
            ):
                result = AgentToolLoopResult(
                    stop_reason="token_budget_exhausted",
                    turns=tuple(turns),
                    error_code="agent_token_budget_exhausted",
                    total_tokens_in=total_in,
                    total_tokens_out=total_out,
                    repeated_action_count=repeated_total,
                )
                self._emit_stop(request, result)
                return _wrap(result, started)

        result = AgentToolLoopResult(
            stop_reason="turn_budget_exhausted",
            turns=tuple(turns),
            error_code="agent_turn_budget_exhausted",
            total_tokens_in=total_in,
            total_tokens_out=total_out,
            repeated_action_count=repeated_total,
        )
        self._emit_stop(request, result)
        return _wrap(result, started)

    def _archive_response(self, request: AgentToolLoopRequest, turn_index: int, text: str) -> None:
        """Persist an unparseable raw response next to events.jsonl."""
        if self.event_writer is None:
            return
        try:
            turns_dir = self.event_writer.path.parent / "agent_turns"
            turns_dir.mkdir(parents=True, exist_ok=True)
            (turns_dir / f"turn_{turn_index:02d}.response.txt").write_text(
                text, encoding="utf-8"
            )
        except OSError:
            pass

    def _emit_tool_call(self, request: AgentToolLoopRequest, turn: AgentLoopTurn) -> None:
        if self.event_writer is None:
            return
        summary = {
            "turn_index": turn.turn_index,
            "action": turn.action_name,
            "ok": turn.observation_ok,
            "error_code": turn.observation_error_code,
            "observation_chars": turn.observation_chars,
            "tokens_in": turn.tokens_in,
            "tokens_out": turn.tokens_out,
            "repeated": turn.repeated_warning,
        }
        if turn.finish_reason is not None:
            summary["finish_reason"] = turn.finish_reason
        if turn.response_excerpt:
            summary["response_excerpt"] = turn.response_excerpt
        self.event_writer.append(
            RunEvent(
                event_id=str(uuid4()),
                run_id=request.task_id,
                task_id=request.task_id,
                phase="agent_loop",
                event_type="tool_call",
                timestamp="",
                summary=summary,
                artifact_refs=(),
            )
        )

    def _emit_stop(self, request: AgentToolLoopRequest, result: AgentToolLoopResult) -> None:
        if self.event_writer is None:
            return
        self.event_writer.append(
            RunEvent(
                event_id=str(uuid4()),
                run_id=request.task_id,
                task_id=request.task_id,
                phase="agent_loop",
                event_type="loop_stopped",
                timestamp="",
                summary={
                    "stop_reason": result.stop_reason,
                    "error_code": result.error_code,
                    "turn_count": len(result.turns),
                    "total_tokens_in": result.total_tokens_in,
                    "total_tokens_out": result.total_tokens_out,
                    "has_proposal": result.proposal is not None,
                },
                artifact_refs=(),
            )
        )


def _compose_prompt(header: str, transcript: list[str]) -> str:
    if not transcript:
        return f"{header}\n\n{_SENTINEL}"
    return f"{header}\n\n" + "\n\n".join(transcript) + f"\n\n{_SENTINEL}"


def _validate_proposal(arguments: dict[str, object], allowed_file_paths: tuple[str, ...]):
    target_file = arguments.get("target_file")
    diff = arguments.get("diff")
    if not isinstance(target_file, str) or not target_file.strip():
        return AgentToolObservation(ok=False, content="propose_patch requires target_file", error_code="invalid_tool_arguments")
    if not isinstance(diff, str) or not diff.strip():
        return AgentToolObservation(ok=False, content="propose_patch requires a non-empty unified diff", error_code="invalid_tool_arguments")
    normalized_allowed = tuple(path.replace("\\", "/") for path in allowed_file_paths)
    if normalized_allowed and target_file.replace("\\", "/") not in normalized_allowed:
        return AgentToolObservation(
            ok=False,
            content=f"target file {target_file} is outside the allowed files",
            error_code="proposal_file_denied",
        )
    return None


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    if isinstance(value, str):
        return (value,)
    return ()


def _arguments_summary(arguments: dict[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for key, value in arguments.items():
        text = str(value)
        summary[key] = text if key == "diff" else text[:120]
    return summary


def _wrap(result: AgentToolLoopResult, started: float) -> CapabilityResult[AgentToolLoopResult]:
    tool_calls: dict[str, int] = {}
    for turn in result.turns:
        tool_calls[turn.action_name] = tool_calls.get(turn.action_name, 0) + 1
    return CapabilityResult(
        capability_name="agent.tool_loop",
        ok=True,
        output=result,
        error=None,
        telemetry=CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=int((perf_counter() - started) * 1000),
            input_summary={"task_id": "", "max_turns_recorded": len(result.turns)},
            output_summary={
                "stop_reason": result.stop_reason,
                "turn_count": len(result.turns),
                "tool_calls": tool_calls,
                "repeated_action_count": result.repeated_action_count,
            },
            token_usage={"input": result.total_tokens_in, "output": result.total_tokens_out},
            model_usage={},
            degraded=result.stop_reason != "proposal_received",
            degradation_reason=None if result.stop_reason == "proposal_received" else result.stop_reason,
        ),
        artifacts=(),
    )
