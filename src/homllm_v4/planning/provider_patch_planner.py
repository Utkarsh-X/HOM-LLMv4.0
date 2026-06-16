from dataclasses import dataclass
from pathlib import Path

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.edit_proposal import (
    EditProposalEvidenceContext,
    EditProposalRequest,
)
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import DirectReadRequest, EvidenceRetrievalRequest, EvidenceSet
from homllm_v4.contracts.patch_plan import EvidenceBackedPatchPlanResult
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.planning.evidence_patch_planner import (
    EvidenceBackedPatchPlanRequest,
    EvidenceBackedPatchPlanner,
)
from homllm_v4.planning.provider_edit_proposer import ProviderBackedEditProposer
from homllm_v4.planning.target_file_selector import (
    EvidenceTargetFileSelector,
    TargetFileSelectionRequest,
    TargetFileSelectionResult,
)
from homllm_v4.services.direct_read_service import DirectReadService
from homllm_v4.services.retrieval_service import EvidenceRetrievalService


@dataclass(frozen=True)
class ProviderProposedPatchPlanRequest:
    task_id: str
    workspace_root: str
    query: str
    task_class: str
    index_id: str
    target_file: str | None
    intent: str
    expected_behavior: str
    verification_argv: tuple[str, ...]
    retrieval_policy: dict[str, object]
    expected_content_hash: str | None = None
    repair_context: str = ""


class ProviderProposedPatchPlanner:
    def __init__(
        self,
        *,
        retrieval_service: EvidenceRetrievalService,
        direct_read_service: DirectReadService,
        edit_proposer: ProviderBackedEditProposer,
        evidence_planner: EvidenceBackedPatchPlanner | None = None,
        target_selector: EvidenceTargetFileSelector | None = None,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.direct_read_service = direct_read_service
        self.edit_proposer = edit_proposer
        self.evidence_planner = evidence_planner or EvidenceBackedPatchPlanner()
        self.target_selector = target_selector or EvidenceTargetFileSelector()

    def plan(
        self,
        request: ProviderProposedPatchPlanRequest,
    ) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
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

        selection: TargetFileSelectionResult | None = None
        target_file = request.target_file
        if target_file is None:
            selection = self.target_selector.select(
                TargetFileSelectionRequest(
                    task_id=request.task_id,
                    evidence_set=retrieval.output,
                )
            )
            if selection.decision != "selected" or selection.target_file is None:
                return _target_selection_failed(request, selection)
            target_file = selection.target_file

        direct_read = self.direct_read_service.read(
            DirectReadRequest(
                task_id=request.task_id,
                file_path=target_file,
                require_hash=True,
            )
        )
        if not direct_read.ok or direct_read.output is None:
            return direct_read

        proposal = self.edit_proposer.propose(
            EditProposalRequest(
                task_id=request.task_id,
                target_file=target_file,
                intent=request.intent,
                expected_behavior=request.expected_behavior,
                current_content=direct_read.output.content_excerpt,
                evidence_ids=tuple(
                    candidate.candidate_id
                    for candidate in retrieval.output.candidates
                    if candidate.file_path == target_file
                ),
                allowed_file_paths=(target_file,),
                verification_summary=" ".join(request.verification_argv),
                evidence_context=_evidence_context_for_target(
                    retrieval.output,
                    target_file,
                ),
                repair_context=request.repair_context,
            )
        )
        if not proposal.ok or proposal.output is None:
            return proposal
        provider_prompt_metrics = _provider_prompt_metrics(proposal.telemetry.output_summary)
        provider_token_usage = proposal.telemetry.token_usage if proposal.telemetry else {}
        provider_model_usage = proposal.telemetry.model_usage if proposal.telemetry else {}

        planned = self.evidence_planner.plan(
            EvidenceBackedPatchPlanRequest(
                task_id=request.task_id,
                workspace_root=str(Path(request.workspace_root)),
                target_file=proposal.output.target_file,
                intent=request.intent,
                expected_behavior=request.expected_behavior,
                evidence_set=retrieval.output,
                direct_reads=(direct_read.output,),
                expected_content_hash=request.expected_content_hash,
                new_content=_preserve_original_trailing_newline(
                    proposal.output.new_content,
                    direct_read.output.content_excerpt,
                ),
                verification_argv=request.verification_argv,
                allowed_file_paths=(target_file,),
            )
        )
        return _with_provider_planner_telemetry(
            planned,
            request=request,
            resolved_target_file=target_file,
            selection=selection,
            provider_prompt_metrics=provider_prompt_metrics,
            provider_token_usage=provider_token_usage,
            provider_model_usage=provider_model_usage,
    )


def _preserve_original_trailing_newline(new_content: str, old_content: str) -> str:
    if old_content.endswith("\n") and not new_content.endswith("\n"):
        return f"{new_content}\n"
    return new_content


def _evidence_context_for_target(
    evidence_set: EvidenceSet,
    target_file: str,
) -> tuple[EditProposalEvidenceContext, ...]:
    return tuple(
        EditProposalEvidenceContext(
            evidence_id=candidate.candidate_id,
            file_path=candidate.file_path,
            span_start=candidate.span_start,
            span_end=candidate.span_end,
            content=str(candidate.metadata.get("content") or ""),
        )
        for candidate in evidence_set.candidates
        if candidate.file_path == target_file
    )


def _target_selection_failed(
    request: ProviderProposedPatchPlanRequest,
    selection: TargetFileSelectionResult,
) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
    code = (
        "target_selection_ambiguous"
        if selection.decision == "ambiguous"
        else "target_selection_failed"
    )
    return CapabilityResult(
        capability_name="patch.plan.provider_proposed",
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


def _with_provider_planner_telemetry(
    result: CapabilityResult[EvidenceBackedPatchPlanResult],
    *,
    request: ProviderProposedPatchPlanRequest,
    resolved_target_file: str,
    selection: TargetFileSelectionResult | None,
    provider_prompt_metrics: dict[str, object],
    provider_token_usage: dict[str, int],
    provider_model_usage: dict[str, object],
) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
    output_summary = dict(result.telemetry.output_summary)
    output_summary.update(provider_prompt_metrics)
    output_summary["resolved_target_file"] = resolved_target_file
    if selection is None:
        output_summary["target_selection_decision"] = "supplied"
    else:
        output_summary["target_selection_decision"] = selection.decision
        output_summary["candidate_file_scores"] = selection.candidate_file_scores
        output_summary["target_selection_confidence"] = selection.confidence

    return CapabilityResult(
        capability_name="patch.plan.provider_proposed",
        ok=result.ok,
        output=result.output,
        error=result.error,
        telemetry=CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=result.telemetry.duration_ms,
            input_summary={
                "task_id": request.task_id,
                "target_file_supplied": request.target_file is not None,
            },
            output_summary=output_summary,
            token_usage=provider_token_usage,
            model_usage=provider_model_usage,
            degraded=result.telemetry.degraded,
            degradation_reason=result.telemetry.degradation_reason,
        ),
        artifacts=result.artifacts,
    )


def _provider_prompt_metrics(output_summary: dict[str, object]) -> dict[str, object]:
    metrics: dict[str, object] = {}
    for key in (
        "prompt_char_count",
        "evidence_context_item_count",
        "evidence_context_rendered_char_count",
        "evidence_context_truncated",
    ):
        if key in output_summary:
            metrics[key] = output_summary[key]
    return metrics
