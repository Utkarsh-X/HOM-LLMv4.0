from dataclasses import dataclass
from time import perf_counter
from uuid import uuid4

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.command import CommandRunRequest
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import DirectReadResult, EvidenceCandidate, EvidenceSet
from homllm_v4.contracts.patch import FilePatch, PatchApplyRequest
from homllm_v4.contracts.patch_plan import EvidenceBackedPatchPlanResult, PatchPlan
from homllm_v4.contracts.telemetry import CapabilityTelemetry


@dataclass(frozen=True)
class EvidenceBackedPatchPlanRequest:
    task_id: str
    workspace_root: str
    target_file: str
    intent: str
    expected_behavior: str
    evidence_set: EvidenceSet
    direct_reads: tuple[DirectReadResult, ...]
    expected_content_hash: str | None
    new_content: str
    verification_argv: tuple[str, ...]
    allowed_file_paths: tuple[str, ...] | None = None
    verification_timeout_seconds: int | None = None


class EvidenceBackedPatchPlanner:
    def plan(
        self,
        request: EvidenceBackedPatchPlanRequest,
    ) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
        started = perf_counter()
        target_evidence = self._target_evidence(request.evidence_set, request.target_file)
        if not target_evidence:
            return self._failed(
                request,
                started,
                "missing_target_evidence",
                f"target file not present in evidence set: {request.target_file}",
            )

        direct_read = self._target_read(request.direct_reads, request.target_file)
        if direct_read is None:
            return self._failed(
                request,
                started,
                "missing_direct_read",
                f"no direct read for target file: {request.target_file}",
            )
        if direct_read.freshness != "fresh":
            return self._failed(
                request,
                started,
                "stale_direct_read",
                f"direct read freshness is {direct_read.freshness}: {request.target_file}",
            )

        expected_hash = request.expected_content_hash or direct_read.content_hash
        if expected_hash is not None and direct_read.content_hash != expected_hash:
            return self._failed(
                request,
                started,
                "stale_context",
                f"direct read hash mismatch for {request.target_file}",
            )

        patch_plan = PatchPlan(
            patch_plan_id=str(uuid4()),
            task_id=request.task_id,
            intent=request.intent,
            target_files=(request.target_file,),
            evidence_ids=tuple(candidate.candidate_id for candidate in target_evidence),
            expected_behavior=request.expected_behavior,
            verification_gates=("stale_context", "diff_safety", "unit_test"),
            risk_flags=(),
            user_visible_summary=f"Patch {request.target_file}: {request.expected_behavior}",
        )
        patch_request = PatchApplyRequest(
            task_id=request.task_id,
            workspace_root=request.workspace_root,
            patches=(
                FilePatch(
                    file_path=request.target_file,
                    expected_content_hash=expected_hash,
                    new_content=request.new_content,
                ),
            ),
            allowed_file_paths=request.allowed_file_paths or (request.target_file,),
            max_file_changes=1,
        )
        # 60s default: real-repo verification (SWE-bench, sympy) can exceed
        # 10s in collection + startup alone. The command service clamps to the
        # policy max (10s for fixture suites, 60s for agent tasks), so this
        # default is safe across both.
        verification = CommandRunRequest(
            task_id=request.task_id,
            workspace_root=request.workspace_root,
            cwd=".",
            argv=request.verification_argv,
            timeout_seconds=(
                60
                if request.verification_timeout_seconds is None
                else max(1, int(request.verification_timeout_seconds))
            ),
        )
        return CapabilityResult(
            capability_name="patch.plan.evidence_backed",
            ok=True,
            output=EvidenceBackedPatchPlanResult(
                patch_plan=patch_plan,
                patch_request=patch_request,
                verification_commands=(verification,),
            ),
            error=None,
            telemetry=self._telemetry(request, started, {"target_file": request.target_file}),
            artifacts=(),
        )

    @staticmethod
    def _target_evidence(evidence_set: EvidenceSet, target_file: str) -> tuple[EvidenceCandidate, ...]:
        return tuple(candidate for candidate in evidence_set.candidates if candidate.file_path == target_file)

    @staticmethod
    def _target_read(
        direct_reads: tuple[DirectReadResult, ...],
        target_file: str,
    ) -> DirectReadResult | None:
        for direct_read in direct_reads:
            if direct_read.file_path == target_file:
                return direct_read
        return None

    def _failed(
        self,
        request: EvidenceBackedPatchPlanRequest,
        started: float,
        code: str,
        message: str,
    ) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
        return CapabilityResult(
            capability_name="patch.plan.evidence_backed",
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
        request: EvidenceBackedPatchPlanRequest,
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
                "evidence_count": len(request.evidence_set.candidates),
                "direct_read_count": len(request.direct_reads),
            },
            output_summary=output_summary,
            token_usage={},
            model_usage={},
            degraded=False,
            degradation_reason=None,
        )
