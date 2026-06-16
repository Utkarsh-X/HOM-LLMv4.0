from dataclasses import dataclass, replace
from typing import Protocol

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.command import CommandRunResult
from homllm_v4.contracts.patch_plan import EvidenceBackedPatchPlanResult
from homllm_v4.contracts.write_loop import WriteVerifyLoopRequest, WriteVerifyStopReason
from homllm_v4.planning.provider_patch_planner import ProviderProposedPatchPlanRequest
from homllm_v4.runtime.write_verify_loop import WriteVerifyLoop


class ProviderPatchPlanner(Protocol):
    def plan(
        self,
        request: ProviderProposedPatchPlanRequest,
    ) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
        ...


@dataclass(frozen=True)
class ProviderWriteVerifyRunRequest:
    task_id: str
    run_id: str
    workspace_root: str
    plan_request: ProviderProposedPatchPlanRequest
    max_verification_commands: int = 1
    provider_repair_attempts: int = 0
    rollback_on_failure: bool = True


@dataclass(frozen=True)
class ProviderWriteVerifyRunResult:
    stop_reason: WriteVerifyStopReason
    error_code: str | None
    verification_results: tuple[CommandRunResult, ...]
    patch_attempt_count: int
    provider_repair_attempt_count: int
    planner_metrics: dict[str, object]
    plan_results: tuple[CapabilityResult[EvidenceBackedPatchPlanResult], ...]
    write_results: tuple[object, ...]


class ProviderWriteVerifyRunner:
    def __init__(
        self,
        *,
        planner: ProviderPatchPlanner,
        write_verify_loop: WriteVerifyLoop,
    ) -> None:
        self.planner = planner
        self.write_verify_loop = write_verify_loop

    def run(self, request: ProviderWriteVerifyRunRequest) -> ProviderWriteVerifyRunResult:
        plan_results: list[CapabilityResult[EvidenceBackedPatchPlanResult]] = []
        write_results = []
        repair_attempt_count = 0
        patch_attempt_count = 0

        plan_result = self._plan(request.plan_request)
        plan_results.append(plan_result)
        if not plan_result.ok or plan_result.output is None:
            return ProviderWriteVerifyRunResult(
                stop_reason="patch_failed",
                error_code=(
                    plan_result.error.code if plan_result.error else "patch_plan_failed"
                ),
                verification_results=(),
                patch_attempt_count=0,
                provider_repair_attempt_count=0,
                planner_metrics=_combined_planner_metrics(tuple(plan_results), 0),
                plan_results=tuple(plan_results),
                write_results=(),
            )

        result = self._run_write_verify(request, plan_result.output)
        write_results.append(result)
        patch_attempt_count += result.patch_attempt_count

        while (
            result.stop_reason in {"verification_failed", "verification_timeout"}
            and repair_attempt_count < max(0, int(request.provider_repair_attempts))
        ):
            repair_attempt_count += 1
            repair_plan_request = replace(
                request.plan_request,
                repair_context=_repair_context(result),
            )
            repair_plan = self._plan(repair_plan_request)
            plan_results.append(repair_plan)
            if not repair_plan.ok or repair_plan.output is None:
                return ProviderWriteVerifyRunResult(
                    stop_reason="patch_failed",
                    error_code=(
                        repair_plan.error.code if repair_plan.error else "patch_plan_failed"
                    ),
                    verification_results=(),
                    patch_attempt_count=patch_attempt_count,
                    provider_repair_attempt_count=repair_attempt_count,
                    planner_metrics=_combined_planner_metrics(
                        tuple(plan_results),
                        repair_attempt_count,
                    ),
                    plan_results=tuple(plan_results),
                    write_results=tuple(write_results),
                )
            result = self._run_write_verify(request, repair_plan.output)
            write_results.append(result)
            patch_attempt_count += result.patch_attempt_count

        return ProviderWriteVerifyRunResult(
            stop_reason=result.stop_reason,
            error_code=result.error.code if result.error else None,
            verification_results=result.verification_results,
            patch_attempt_count=patch_attempt_count,
            provider_repair_attempt_count=repair_attempt_count,
            planner_metrics=_combined_planner_metrics(
                tuple(plan_results),
                repair_attempt_count,
            ),
            plan_results=tuple(plan_results),
            write_results=tuple(write_results),
        )

    def _plan(
        self,
        request: ProviderProposedPatchPlanRequest,
    ) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
        return self.planner.plan(request)

    def _run_write_verify(
        self,
        request: ProviderWriteVerifyRunRequest,
        plan_result: EvidenceBackedPatchPlanResult,
    ):
        return self.write_verify_loop.run(
            WriteVerifyLoopRequest(
                task_id=request.task_id,
                run_id=request.run_id,
                workspace_root=request.workspace_root,
                patch_request=plan_result.patch_request,
                verification_commands=plan_result.verification_commands,
                max_verification_commands=request.max_verification_commands,
                max_patch_attempts=1,
                rollback_on_failure=request.rollback_on_failure,
            )
        )


def _combined_planner_metrics(
    plan_results: tuple[CapabilityResult[EvidenceBackedPatchPlanResult], ...],
    provider_repair_attempt_count: int,
) -> dict[str, object]:
    if not plan_results:
        return {"provider_repair_attempt_count": provider_repair_attempt_count}

    combined = _planner_metrics(plan_results[-1])
    for key in (
        "provider_tokens_in",
        "provider_tokens_out",
        "prompt_char_count",
        "evidence_context_item_count",
        "evidence_context_rendered_char_count",
    ):
        total = 0
        seen = False
        for plan_result in plan_results:
            metrics = _planner_metrics(plan_result)
            if key in metrics:
                total += int(metrics[key])
                seen = True
        if seen:
            combined[key] = total
    combined["provider_repair_attempt_count"] = provider_repair_attempt_count
    return combined


def _planner_metrics(
    plan_result: CapabilityResult[EvidenceBackedPatchPlanResult],
) -> dict[str, object]:
    if plan_result.telemetry is None:
        return {}
    output = plan_result.telemetry.output_summary
    metrics: dict[str, object] = {}
    token_usage = plan_result.telemetry.token_usage
    if token_usage:
        metrics["provider_tokens_in"] = int(token_usage.get("input", 0))
        metrics["provider_tokens_out"] = int(token_usage.get("output", 0))
    for key in (
        "target_selection_decision",
        "planner_context_mode",
        "resolved_target_file",
        "target_selection_confidence",
        "prompt_char_count",
        "evidence_context_item_count",
        "evidence_context_rendered_char_count",
        "evidence_context_truncated",
    ):
        if key in output:
            metrics[key] = output[key]
    candidate_file_scores = output.get("candidate_file_scores")
    if isinstance(candidate_file_scores, dict):
        metrics["candidate_file_score_count"] = len(candidate_file_scores)
    return metrics


def _repair_context(result) -> str:
    lines = [f"Previous verification stopped with reason {result.stop_reason}."]
    if result.verification_results:
        last = result.verification_results[-1]
        lines.append(
            "Last verification result: "
            f"exit_code={last.exit_code}, timed_out={last.timed_out}, "
            f"stdout={_truncate_diagnostic(last.stdout)}, "
            f"stderr={_truncate_diagnostic(last.stderr)}."
        )
    return " ".join(lines)


def _truncate_diagnostic(text: str, limit: int = 500) -> str:
    normalized = text.replace("\r\n", "\n").replace("\n", "\\n")
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}...[truncated]"
