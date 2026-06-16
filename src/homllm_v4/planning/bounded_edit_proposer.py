from collections.abc import Callable
from time import perf_counter

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.edit_proposal import EditProposalRequest, EditProposalResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import DirectReadResult, EvidenceSet
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.planning.evidence_patch_planner import EvidenceBackedPatchPlanRequest

ProposalCallable = Callable[[EditProposalRequest], EditProposalResult]


class BoundedEditProposer:
    def __init__(self, *, proposer: ProposalCallable) -> None:
        self.proposer = proposer

    def propose(self, request: EditProposalRequest) -> CapabilityResult[EditProposalResult]:
        started = perf_counter()
        try:
            proposal = self.proposer(request)
        except Exception as exc:
            return self._failed(request, started, "proposal_failed", str(exc))

        if proposal.target_file not in request.allowed_file_paths:
            return self._failed(
                request,
                started,
                "proposal_file_denied",
                f"proposal targets unapproved file: {proposal.target_file}",
            )
        if not proposal.new_content:
            return self._failed(
                request,
                started,
                "proposal_empty_content",
                "proposal new_content is empty",
            )
        if not proposal.evidence_ids:
            return self._failed(
                request,
                started,
                "proposal_missing_evidence",
                "proposal did not retain supporting evidence ids",
            )

        return CapabilityResult(
            capability_name="edit.propose.bounded",
            ok=True,
            output=proposal,
            error=None,
            telemetry=self._telemetry(
                request,
                started,
                {
                    "target_file": proposal.target_file,
                    "risk_flags": proposal.risk_flags,
                },
            ),
            artifacts=(),
        )

    def _failed(
        self,
        request: EditProposalRequest,
        started: float,
        code: str,
        message: str,
    ) -> CapabilityResult[EditProposalResult]:
        return CapabilityResult(
            capability_name="edit.propose.bounded",
            ok=False,
            output=None,
            error=CapabilityError(
                code=code,
                message=message,
                recoverable=True,
                retryable=False,
                details={"target_file": request.target_file},
            ),
            telemetry=self._telemetry(request, started, {"code": code}),
            artifacts=(),
        )

    @staticmethod
    def _telemetry(
        request: EditProposalRequest,
        started: float,
        output_summary: dict[str, object],
    ) -> CapabilityTelemetry:
        return CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=int((perf_counter() - started) * 1000),
            input_summary={
                "task_id": request.task_id,
                "target_file": request.target_file,
                "evidence_count": len(request.evidence_ids),
            },
            output_summary=output_summary,
            token_usage={},
            model_usage={},
            degraded=False,
            degradation_reason=None,
        )


def evidence_plan_request_from_proposal(
    *,
    task_id: str,
    workspace_root: str,
    intent: str,
    expected_behavior: str,
    evidence_set: EvidenceSet,
    direct_read: DirectReadResult,
    proposal: EditProposalResult,
    verification_argv: tuple[str, ...],
) -> EvidenceBackedPatchPlanRequest:
    return EvidenceBackedPatchPlanRequest(
        task_id=task_id,
        workspace_root=workspace_root,
        target_file=proposal.target_file,
        intent=intent,
        expected_behavior=expected_behavior,
        evidence_set=evidence_set,
        direct_reads=(direct_read,),
        expected_content_hash=direct_read.content_hash,
        new_content=proposal.new_content,
        verification_argv=verification_argv,
        allowed_file_paths=(proposal.target_file,),
    )
