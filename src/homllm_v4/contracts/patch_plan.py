from dataclasses import dataclass

from homllm_v4.contracts.command import CommandRunRequest
from homllm_v4.contracts.patch import PatchApplyRequest


@dataclass(frozen=True)
class PatchPlan:
    patch_plan_id: str
    task_id: str
    intent: str
    target_files: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    expected_behavior: str
    verification_gates: tuple[str, ...]
    risk_flags: tuple[str, ...]
    user_visible_summary: str


@dataclass(frozen=True)
class EvidenceBackedPatchPlanResult:
    patch_plan: PatchPlan
    patch_request: PatchApplyRequest
    verification_commands: tuple[CommandRunRequest, ...]
