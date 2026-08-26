from time import perf_counter

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.edit_proposal import EditProposalRequest
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import (
    DirectReadRequest,
    EvidenceCandidate,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.contracts.patch_plan import EvidenceBackedPatchPlanResult
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.planning.evidence_patch_planner import (
    EvidenceBackedPatchPlanRequest,
    EvidenceBackedPatchPlanner,
)
from homllm_v4.planning.provider_edit_proposer import ProviderBackedEditProposer
from homllm_v4.planning.provider_patch_planner import ProviderProposedPatchPlanRequest
from homllm_v4.planning.seed_evidence import preserve_original_trailing_newline
from homllm_v4.services.direct_read_service import DirectReadService


class DirectProviderPatchPlanner:
    def __init__(
        self,
        *,
        direct_read_service: DirectReadService,
        edit_proposer: ProviderBackedEditProposer,
        evidence_planner: EvidenceBackedPatchPlanner | None = None,
    ) -> None:
        self.direct_read_service = direct_read_service
        self.edit_proposer = edit_proposer
        self.evidence_planner = evidence_planner or EvidenceBackedPatchPlanner()

    def plan(
        self,
        request: ProviderProposedPatchPlanRequest,
    ) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
        started = perf_counter()
        if request.target_file is None:
            return _target_required(request, started)

        target_file = request.target_file
        direct_read = self.direct_read_service.read(
            DirectReadRequest(
                task_id=request.task_id,
                file_path=target_file,
                require_hash=True,
            )
        )
        if not direct_read.ok or direct_read.output is None:
            return direct_read

        evidence_set = _synthetic_evidence_set(request, target_file, direct_read.output.content_hash)
        proposal = self.edit_proposer.propose(
            EditProposalRequest(
                task_id=request.task_id,
                target_file=target_file,
                intent=request.intent,
                expected_behavior=request.expected_behavior,
                current_content=direct_read.output.content_excerpt,
                evidence_ids=tuple(candidate.candidate_id for candidate in evidence_set.candidates),
                allowed_file_paths=(target_file,),
                verification_summary=" ".join(request.verification_argv),
                evidence_context=(),
                repair_context=request.repair_context,
            )
        )
        if not proposal.ok or proposal.output is None:
            return proposal

        planned = self.evidence_planner.plan(
            EvidenceBackedPatchPlanRequest(
                task_id=request.task_id,
                workspace_root=request.workspace_root,
                target_file=proposal.output.target_file,
                intent=request.intent,
                expected_behavior=request.expected_behavior,
                evidence_set=evidence_set,
                direct_reads=(direct_read.output,),
                expected_content_hash=request.expected_content_hash,
                new_content=preserve_original_trailing_newline(
                    proposal.output.new_content,
                    direct_read.output.content_excerpt,
                ),
                verification_argv=request.verification_argv,
                allowed_file_paths=(target_file,),
            )
        )
        return _with_direct_provider_telemetry(
            planned,
            request=request,
            started=started,
            resolved_target_file=target_file,
            proposal_summary=proposal.telemetry.output_summary if proposal.telemetry else {},
            provider_token_usage=proposal.telemetry.token_usage if proposal.telemetry else {},
            provider_model_usage=proposal.telemetry.model_usage if proposal.telemetry else {},
        )


def _target_required(
    request: ProviderProposedPatchPlanRequest,
    started: float,
) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
    return CapabilityResult(
        capability_name="patch.plan.direct_provider",
        ok=False,
        output=None,
        error=CapabilityError(
            code="direct_provider_target_required",
            message="direct-provider planner requires a supplied target_file",
            recoverable=True,
            retryable=False,
            details={"task_id": request.task_id},
        ),
        telemetry=CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=int((perf_counter() - started) * 1000),
            input_summary={"task_id": request.task_id, "target_file_supplied": False},
            output_summary={
                "code": "direct_provider_target_required",
                "planner_context_mode": "direct_provider",
            },
            token_usage={},
            model_usage={},
            degraded=False,
            degradation_reason=None,
        ),
        artifacts=(),
    )


def _synthetic_evidence_set(
    request: ProviderProposedPatchPlanRequest,
    target_file: str,
    content_hash: str | None,
) -> EvidenceSet:
    return EvidenceSet(
        evidence_set_id=f"{request.task_id}:direct-provider-evidence",
        query=request.query,
        candidates=(
            EvidenceCandidate(
                candidate_id=f"{request.task_id}:direct:{target_file}",
                file_path=target_file,
                symbol_id=None,
                span_start=1,
                span_end=None,
                content_hash=content_hash or "",
                source_channels=("direct_provider",),
                bm25_score=None,
                vector_score=None,
                graph_score=None,
                retrieval_score=1.0,
                metadata={"planner_context_mode": "direct_provider"},
            ),
        ),
        diagnostics=RetrievalDiagnostics(
            bm25_count=0,
            vector_count=0,
            graph_added_count=0,
            precision_added_count=0,
            coverage_added_count=1,
            retrieval_disagreement=None,
            degraded=False,
            degradation_reason=None,
        ),
    )


def _with_direct_provider_telemetry(
    result: CapabilityResult[EvidenceBackedPatchPlanResult],
    *,
    request: ProviderProposedPatchPlanRequest,
    started: float,
    resolved_target_file: str,
    proposal_summary: dict[str, object],
    provider_token_usage: dict[str, int],
    provider_model_usage: dict[str, object],
) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
    output_summary = dict(result.telemetry.output_summary) if result.telemetry else {}
    for key in (
        "prompt_char_count",
        "evidence_context_item_count",
        "evidence_context_rendered_char_count",
        "evidence_context_truncated",
    ):
        if key in proposal_summary:
            output_summary[key] = proposal_summary[key]
    output_summary.update(
        {
            "planner_context_mode": "direct_provider",
            "resolved_target_file": resolved_target_file,
            "target_selection_decision": "direct_supplied",
        }
    )
    return CapabilityResult(
        capability_name="patch.plan.direct_provider",
        ok=result.ok,
        output=result.output,
        error=result.error,
        telemetry=CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=int((perf_counter() - started) * 1000),
            input_summary={
                "task_id": request.task_id,
                "target_file_supplied": request.target_file is not None,
            },
            output_summary=output_summary,
            token_usage=provider_token_usage,
            model_usage=provider_model_usage,
            degraded=result.telemetry.degraded if result.telemetry else False,
            degradation_reason=result.telemetry.degradation_reason if result.telemetry else None,
        ),
        artifacts=result.artifacts,
    )
