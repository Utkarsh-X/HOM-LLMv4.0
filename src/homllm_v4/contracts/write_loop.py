from dataclasses import dataclass
from typing import Literal

from homllm_v4.contracts.command import CommandRunRequest, CommandRunResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.patch import PatchApplyRequest, PatchApplyResult, PatchRollbackResult

WriteVerifyStopReason = Literal[
    "verified",
    "patch_failed",
    "verification_failed",
    "verification_side_effect",
    "verification_timeout",
    "budget_exhausted",
    "repair_budget_exhausted",
]


@dataclass(frozen=True)
class WriteVerifyLoopRequest:
    task_id: str
    run_id: str
    workspace_root: str
    patch_request: PatchApplyRequest
    verification_commands: tuple[CommandRunRequest, ...]
    max_verification_commands: int = 3
    repair_patch_requests: tuple[PatchApplyRequest, ...] = ()
    max_patch_attempts: int = 1
    rollback_on_failure: bool = False


@dataclass(frozen=True)
class WriteVerifyLoopResult:
    task_id: str
    run_id: str
    stop_reason: WriteVerifyStopReason
    patch_result: PatchApplyResult | None
    verification_results: tuple[CommandRunResult, ...]
    response_text: str
    patch_attempt_count: int = 0
    error: CapabilityError | None = None
    rollback_result: PatchRollbackResult | None = None
