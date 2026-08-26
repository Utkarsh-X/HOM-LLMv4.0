"""Agentic-loop patch planner.

Implements the same ``ProviderPatchPlanner`` protocol as
:class:`~homllm_v4.planning.provider_patch_planner.ProviderProposedPatchPlanner`
but replaces the single-shot proposal with a bounded model-driven tool loop.
Seed evidence, target selection, hash-gated direct reads, and final plan
assembly are shared with the single-shot path; only evidence *acquisition*
becomes agentic. See docs/v4_architecture/12-agentic-loop-upgrade-plan.md.
"""

from dataclasses import replace as dataclass_replace
from time import perf_counter

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.edit_proposal import EditProposalEvidenceContext
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import DirectReadRequest, EvidenceRetrievalRequest
from homllm_v4.contracts.patch_plan import EvidenceBackedPatchPlanResult
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.planning.agent_loop_prompts import make_agent_tool_loop_request
from homllm_v4.planning.evidence_patch_planner import (
    EvidenceBackedPatchPlanRequest,
    EvidenceBackedPatchPlanner,
)
from homllm_v4.planning.provider_patch_planner import ProviderProposedPatchPlanRequest
from homllm_v4.planning.seed_evidence import (
    best_retrieval_score,
    build_target_section_fallback_candidates,
    preserve_original_trailing_newline,
)
from homllm_v4.planning.target_file_selector import (
    EvidenceTargetFileSelector,
    TargetFileSelectionRequest,
)
from homllm_v4.runtime.agent_tool_loop import BoundedAgentToolLoop
from homllm_v4.runtime.agent_tools import AgentToolExecutor
from homllm_v4.services.direct_read_service import DirectReadService
from homllm_v4.services.retrieval_service import EvidenceRetrievalService
from homllm_v4.utils.unified_diff import apply_unified_diff


class AgenticLoopPatchPlanner:
    def __init__(
        self,
        *,
        retrieval_service: EvidenceRetrievalService,
        direct_read_service: DirectReadService,
        edit_provider: object,
        evidence_planner: EvidenceBackedPatchPlanner | None = None,
        target_selector: EvidenceTargetFileSelector | None = None,
        event_writer: object | None = None,
        default_max_turns: int = 10,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.direct_read_service = direct_read_service
        self.edit_provider = edit_provider
        self.evidence_planner = evidence_planner or EvidenceBackedPatchPlanner()
        self.target_selector = target_selector or EvidenceTargetFileSelector()
        self.event_writer = event_writer
        self.default_max_turns = max(1, int(default_max_turns))

    def plan(
        self,
        request: ProviderProposedPatchPlanRequest,
    ) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
        started = perf_counter()

        retrieval = self.retrieval_service.retrieve(
            EvidenceRetrievalRequest(
                task_id=request.task_id,
                query=request.query,
                task_class=request.task_class,
                index_id=request.index_id,
                policy=request.retrieval_policy,
                target_files=(request.target_file,) if request.target_file else (),
            )
        )
        if not retrieval.ok or retrieval.output is None:
            return retrieval

        selection = None
        target_file = request.target_file
        if target_file is None:
            selection_result = self.target_selector.select(
                TargetFileSelectionRequest(
                    task_id=request.task_id,
                    evidence_set=retrieval.output,
                )
            )
            selection = selection_result
            if selection_result.decision != "selected" or selection_result.target_file is None:
                return _selection_failed(request, selection_result)
            target_file = selection_result.target_file

        direct_read = self.direct_read_service.read(
            DirectReadRequest(
                task_id=request.task_id,
                file_path=target_file,
                require_hash=True,
            )
        )
        if not direct_read.ok or direct_read.output is None:
            return direct_read

        has_evidence_for_target = any(
            candidate.file_path == target_file for candidate in retrieval.output.candidates
        )
        if has_evidence_for_target:
            seed_candidates = tuple(
                candidate
                for candidate in retrieval.output.candidates
                if candidate.file_path == target_file
            )
        else:
            seed_candidates = build_target_section_fallback_candidates(
                target_file=target_file,
                content=direct_read.output.content_excerpt or "",
                query=request.query,
                context=" ".join((request.intent, request.expected_behavior)),
                full_content_hash=direct_read.output.content_hash or "",
            )

        executor = AgentToolExecutor(
            retrieval_service=self.retrieval_service,
            direct_read_service=self.direct_read_service,
            index_id=request.index_id,
        )
        loop = BoundedAgentToolLoop(
            provider=self.edit_provider,
            executor=executor,
            event_writer=self.event_writer,
        )
        loop_result_capability = loop.run(
            make_agent_tool_loop_request(
                task_id=request.task_id,
                query=request.query,
                intent=request.intent,
                expected_behavior=request.expected_behavior,
                verification_summary=" ".join(request.verification_argv),
                evidence_context=evidence_context_from(seed_candidates),
                target_file=target_file,
                allowed_file_paths=(target_file,),
                repair_context=request.repair_context,
                proposal_mode=request.proposal_mode,
                max_turns=max(1, int(request.max_agent_turns or self.default_max_turns)),
            )
        )
        loop_result = loop_result_capability.output

        if loop_result.proposal is None:
            retryable = loop_result.stop_reason in {
                "finished_without_patch",
                "provider_error",
            }
            code = loop_result.error_code or f"agent_{loop_result.stop_reason}"
            return CapabilityResult(
                capability_name="patch.plan.agentic_loop",
                ok=False,
                output=None,
                error=CapabilityError(
                    code=code,
                    message=loop_result.error_message or loop_result.stop_reason,
                    recoverable=True,
                    retryable=retryable,
                    details=_agent_details(loop_result),
                ),
                telemetry=_agent_telemetry(loop_result_capability.telemetry, loop_result, started),
                artifacts=(),
            )

        proposal = loop_result.proposal
        if proposal.target_file != target_file:
            return CapabilityResult(
                capability_name="patch.plan.agentic_loop",
                ok=False,
                output=None,
                error=CapabilityError(
                    code="proposal_file_denied",
                    message=(
                        f"agent proposed {proposal.target_file} but resolved target is {target_file}"
                    ),
                    recoverable=True,
                    retryable=False,
                    details={"proposed": proposal.target_file, "resolved": target_file},
                ),
                telemetry=_agent_telemetry(loop_result_capability.telemetry, loop_result, started),
                artifacts=(),
            )

        try:
            applied_content = apply_unified_diff(direct_read.output.content_excerpt, proposal.diff)
        except ValueError as exc:
            return CapabilityResult(
                capability_name="patch.plan.agentic_loop",
                ok=False,
                output=None,
                error=CapabilityError(
                    code="provider_diff_not_applicable",
                    message=str(exc),
                    recoverable=True,
                    retryable=True,
                    details=_agent_details(loop_result),
                ),
                telemetry=_agent_telemetry(loop_result_capability.telemetry, loop_result, started),
                artifacts=(),
            )

        planned = self.evidence_planner.plan(
            EvidenceBackedPatchPlanRequest(
                task_id=request.task_id,
                workspace_root=str(request.workspace_root),
                target_file=target_file,
                intent=request.intent,
                expected_behavior=request.expected_behavior,
                evidence_set=retrieval.output,
                direct_reads=(direct_read.output,),
                expected_content_hash=request.expected_content_hash,
                new_content=preserve_original_trailing_newline(
                    applied_content,
                    direct_read.output.content_excerpt,
                ),
                verification_argv=request.verification_argv,
                allowed_file_paths=(target_file,),
                verification_timeout_seconds=request.verification_timeout_seconds,
            )
        )
        return _with_agent_planner_telemetry(
            planned,
            request=request,
            loop_capability=loop_result_capability,
            resolved_target_file=target_file,
            target_evidence_retrieved=has_evidence_for_target,
            target_file_retrieval_score=best_retrieval_score(
                retrieval.output.candidates,
                target_file,
            ),
            retrieved_evidence_count=len(retrieval.output.candidates),
            selection_decision="supplied" if request.target_file else (selection.decision if selection else "supplied"),
        )


def evidence_context_from(candidates):
    return tuple(
        EditProposalEvidenceContext(
            evidence_id=candidate.candidate_id,
            file_path=candidate.file_path,
            span_start=candidate.span_start,
            span_end=candidate.span_end,
            content=str(candidate.metadata.get("content") or ""),
        )
        for candidate in candidates
    )


def _agent_details(loop_result):
    return {
        "stop_reason": loop_result.stop_reason,
        "turn_count": len(loop_result.turns),
        "total_tokens_in": loop_result.total_tokens_in,
        "total_tokens_out": loop_result.total_tokens_out,
        "repeated_action_count": loop_result.repeated_action_count,
    }


def _agent_telemetry(base_telemetry, loop_result, started) -> CapabilityTelemetry:
    token_usage = dict(base_telemetry.token_usage) if base_telemetry else {}
    return CapabilityTelemetry(
        started_at="",
        ended_at="",
        duration_ms=int((perf_counter() - started) * 1000),
        input_summary={"task_id": ""},
        output_summary={
            "stop_reason": loop_result.stop_reason,
            "turn_count": len(loop_result.turns),
            "repeated_action_count": loop_result.repeated_action_count,
        },
        token_usage=token_usage,
        model_usage={},
        degraded=loop_result.stop_reason != "proposal_received",
        degradation_reason=(
            None if loop_result.stop_reason == "proposal_received" else loop_result.stop_reason
        ),
    )


def _with_agent_planner_telemetry(
    result: CapabilityResult[EvidenceBackedPatchPlanResult],
    *,
    request: ProviderProposedPatchPlanRequest,
    loop_capability: CapabilityResult,
    resolved_target_file: str,
    target_evidence_retrieved: bool,
    target_file_retrieval_score: float | None,
    retrieved_evidence_count: int,
    selection_decision: str,
) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
    loop_output = loop_capability.output
    output_summary = dict(result.telemetry.output_summary)
    output_summary["agent_stop_reason"] = loop_output.stop_reason
    output_summary["agent_turn_count"] = len(loop_output.turns)
    output_summary["agent_repeated_actions"] = loop_output.repeated_action_count
    tool_calls: dict[str, int] = {}
    for turn in loop_output.turns:
        tool_calls[turn.action_name] = tool_calls.get(turn.action_name, 0) + 1
    output_summary["agent_tool_calls"] = tool_calls
    output_summary["resolved_target_file"] = resolved_target_file
    output_summary["target_evidence_retrieved"] = target_evidence_retrieved
    if target_file_retrieval_score is not None:
        output_summary["target_file_retrieval_score"] = target_file_retrieval_score
    output_summary["retrieved_evidence_count"] = retrieved_evidence_count
    output_summary["target_selection_decision"] = selection_decision

    merged_tokens = dict(loop_capability.telemetry.token_usage)
    for key in ("input", "output"):
        existing = int(result.telemetry.token_usage.get(key, 0))
        merged = int(merged_tokens.get(key, 0)) + existing
        merged_tokens[key] = merged

    return CapabilityResult(
        capability_name=result.capability_name,
        ok=result.ok,
        output=result.output,
        error=result.error,
        telemetry=dataclass_replace(
            result.telemetry,
            duration_ms=int(result.telemetry.duration_ms + loop_capability.telemetry.duration_ms),
            output_summary=output_summary,
            token_usage=merged_tokens,
        ),
        artifacts=result.artifacts,
    )


def _selection_failed(request, selection) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
    code = (
        "target_selection_ambiguous"
        if selection.decision == "ambiguous"
        else "target_selection_failed"
    )
    return CapabilityResult(
        capability_name="patch.plan.agentic_loop",
        ok=False,
        output=None,
        error=CapabilityError(
            code=code,
            message=selection.reason or "target file selection failed",
            recoverable=True,
            retryable=False,
            details={
                "decision": selection.decision,
                "candidate_file_scores": selection.candidate_file_scores,
            },
        ),
        telemetry=CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=0,
            input_summary={"task_id": request.task_id},
            output_summary={
                "selection_decision": selection.decision,
                "selection_reason": selection.reason,
            },
            token_usage={},
            model_usage={},
            degraded=False,
            degradation_reason=None,
        ),
        artifacts=(),
    )
