from dataclasses import dataclass
from pathlib import Path

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.evidence import DirectReadRequest, EvidenceRetrievalRequest
from homllm_v4.contracts.patch_plan import EvidenceBackedPatchPlanResult
from homllm_v4.planning.evidence_patch_planner import (
    EvidenceBackedPatchPlanRequest,
    EvidenceBackedPatchPlanner,
)
from homllm_v4.services.direct_read_service import DirectReadService
from homllm_v4.services.retrieval_service import EvidenceRetrievalService


@dataclass(frozen=True)
class RetrievalBackedPatchPlanRequest:
    task_id: str
    workspace_root: str
    query: str
    task_class: str
    index_id: str
    target_file: str
    intent: str
    expected_behavior: str
    new_content: str
    verification_argv: tuple[str, ...]
    retrieval_policy: dict[str, object]
    expected_content_hash: str | None = None


class RetrievalBackedPatchPlanner:
    def __init__(
        self,
        *,
        retrieval_service: EvidenceRetrievalService,
        direct_read_service: DirectReadService,
        evidence_planner: EvidenceBackedPatchPlanner | None = None,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.direct_read_service = direct_read_service
        self.evidence_planner = evidence_planner or EvidenceBackedPatchPlanner()

    def plan(
        self,
        request: RetrievalBackedPatchPlanRequest,
    ) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
        retrieval = self.retrieval_service.retrieve(
            EvidenceRetrievalRequest(
                task_id=request.task_id,
                query=request.query,
                task_class=request.task_class,
                index_id=request.index_id,
                policy=request.retrieval_policy,
                target_files=(request.target_file,),
            )
        )
        if not retrieval.ok or retrieval.output is None:
            return retrieval

        direct_read = self.direct_read_service.read(
            DirectReadRequest(
                task_id=request.task_id,
                file_path=request.target_file,
                require_hash=True,
            )
        )
        if not direct_read.ok or direct_read.output is None:
            return direct_read

        return self.evidence_planner.plan(
            EvidenceBackedPatchPlanRequest(
                task_id=request.task_id,
                workspace_root=str(Path(request.workspace_root)),
                target_file=request.target_file,
                intent=request.intent,
                expected_behavior=request.expected_behavior,
                evidence_set=retrieval.output,
                direct_reads=(direct_read.output,),
                expected_content_hash=request.expected_content_hash,
                new_content=request.new_content,
                verification_argv=request.verification_argv,
                allowed_file_paths=(request.target_file,),
            )
        )
