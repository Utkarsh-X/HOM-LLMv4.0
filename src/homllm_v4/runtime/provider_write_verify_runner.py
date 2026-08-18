import difflib
import hashlib
import re
from dataclasses import dataclass, replace
from pathlib import Path
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
        max_repairs = max(0, int(request.provider_repair_attempts))

        plan_request = request.plan_request
        plan_result = self._plan(plan_request)
        plan_results.append(plan_result)
        while (
            (not plan_result.ok or plan_result.output is None)
            and repair_attempt_count < max_repairs
            and _plan_retryable(plan_result)
        ):
            repair_attempt_count += 1
            plan_request = replace(
                request.plan_request,
                repair_context=_plan_repair_context(plan_result),
            )
            plan_result = self._plan(plan_request)
            plan_results.append(plan_result)
        if not plan_result.ok or plan_result.output is None:
            return ProviderWriteVerifyRunResult(
                stop_reason="patch_failed",
                error_code=(
                    plan_result.error.code if plan_result.error else "patch_plan_failed"
                ),
                verification_results=(),
                patch_attempt_count=0,
                provider_repair_attempt_count=repair_attempt_count,
                planner_metrics=_combined_planner_metrics(
                    tuple(plan_results),
                    repair_attempt_count,
                ),
                plan_results=tuple(plan_results),
                write_results=(),
            )

        result = self._run_write_verify(request, plan_result.output)
        write_results.append(result)
        patch_attempt_count += result.patch_attempt_count

        while (
            result.stop_reason in {"verification_failed", "verification_timeout"}
            and repair_attempt_count < max_repairs
        ):
            repair_attempt_count += 1
            previous_plan = plan_result
            repair_plan_request = replace(
                request.plan_request,
                repair_context=_repair_context(
                    result,
                    previous_plan=previous_plan,
                ),
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
            plan_result = repair_plan
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
        "target_evidence_retrieved",
        "target_file_retrieval_score",
        "retrieved_evidence_count",
        "prompt_char_count",
        "evidence_context_item_count",
        "evidence_context_rendered_char_count",
        "evidence_context_truncated",
        "current_content_char_count",
        "current_content_truncated",
    ):
        if key in output:
            metrics[key] = output[key]
    candidate_file_scores = output.get("candidate_file_scores")
    if isinstance(candidate_file_scores, dict):
        metrics["candidate_file_score_count"] = len(candidate_file_scores)
    return metrics


_PLAN_RETRYABLE_CODES = frozenset(
    {
        "provider_invocation_failed",
        "provider_response_invalid",
        "provider_response_truncated",
        "proposal_evidence_scope_denied",
        "proposal_missing_evidence",
    }
)


def _plan_retryable(
    plan_result: CapabilityResult[EvidenceBackedPatchPlanResult],
) -> bool:
    """Return True when a failed plan attempt is worth re-running.

    Retryable failures are provider-output problems (transient invocation
    errors, malformed/truncated JSON, unapproved evidence ids) that a fresh
    provider call can plausibly fix. Deterministic failures (bad target
    selection, missing files) are not retried -- they will fail identically.
    """
    if plan_result.ok or plan_result.error is None:
        return False
    if plan_result.error.retryable:
        return True
    return plan_result.error.code in _PLAN_RETRYABLE_CODES


def _plan_repair_context(
    plan_result: CapabilityResult[EvidenceBackedPatchPlanResult],
) -> str:
    error = plan_result.error
    code = error.code if error is not None else "patch_plan_failed"
    message = error.message if error is not None else "plan failed"
    return (
        "Previous provider edit proposal failed with code "
        f"{code}: {_truncate_diagnostic(message)}. "
        "Return valid JSON with the required keys (target_file, new_content, "
        "rationale, evidence_ids, risk_flags)."
    )


def _repair_context(result, *, previous_plan=None) -> str:
    lines = [f"Previous verification stopped with reason {result.stop_reason}."]
    if result.verification_results:
        last = result.verification_results[-1]
        failure_summary = _pytest_failure_summary(last)
        if failure_summary is not None:
            lines.append(failure_summary)
        else:
            lines.append(
                "Last verification result: "
                f"exit_code={last.exit_code}, timed_out={last.timed_out}, "
                f"stdout={_tail_diagnostic(last.stdout)}, "
                f"stderr={_tail_diagnostic(last.stderr)}."
            )
    if previous_plan is not None:
        attempt_diff = _previous_attempt_diff(previous_plan)
        if attempt_diff is not None:
            lines.append(attempt_diff)
    return " ".join(lines)


_PREVIOUS_ATTEMPT_DIFF_LIMIT = 3000


def _previous_attempt_diff(plan_result) -> str | None:
    """Build a compact diff of the previous failed attempt for the repair prompt.

    The model re-plans after a verification failure without seeing what it
    proposed, so a budget model tends to repeat the same wrong edit. Showing
    the exact change it applied (previous new_content vs. the rolled-back
    original) lets the next attempt correct the specific mistake instead of
    re-deriving it. Returns None when the workspace no longer holds the
    original content (no rollback) or the diff is empty.
    """
    output = getattr(plan_result, "output", None)
    patch_request = getattr(output, "patch_request", None)
    if patch_request is None:
        return None
    patches = tuple(getattr(patch_request, "patches", ()))
    if not patches:
        return None
    patch = patches[0]
    new_content = getattr(patch, "new_content", None)
    if not isinstance(new_content, str):
        return None
    workspace_root = Path(str(getattr(patch_request, "workspace_root", "")))
    if not workspace_root.is_absolute():
        return None
    try:
        path = (workspace_root / str(getattr(patch, "file_path", ""))).resolve()
        path.relative_to(workspace_root.resolve())
        original = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    expected_hash = getattr(patch, "expected_content_hash", None)
    if expected_hash is not None:
        normalized = original.replace("\r\n", "\n").encode("utf-8")
        if hashlib.sha256(normalized).hexdigest() != str(expected_hash):
            return None
    if original == new_content:
        return None
    file_path = str(getattr(patch, "file_path", "file"))
    diff_lines = list(
        difflib.unified_diff(
            original.splitlines(),
            new_content.splitlines(),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        )
    )
    if not diff_lines:
        return None
    rendered = "\n".join(diff_lines)
    if len(rendered) > _PREVIOUS_ATTEMPT_DIFF_LIMIT:
        rendered = rendered[: _PREVIOUS_ATTEMPT_DIFF_LIMIT] + "\n...[diff truncated]"
    return (
        "Your previous attempt applied this diff (rolled back before this "
        f"attempt):\n{rendered}"
    )


_PYTEST_SUMMARY_LINE_RE = re.compile(r"\b\d+ (?:failed|passed|error|skipped)\b")


def _pytest_failure_summary(result) -> str | None:
    """Extract a compact pytest failure summary for the repair prompt.

    Pytest's ``-q`` output puts the actionable failure info (``FAILED`` lines
    with node ids and reasons) in the short test summary at the *end* of the
    output, while the beginning is traceback head noise. When the last
    verification result looks like pytest output, return a short
    "Failing tests:" block the model can act on instead of raw head-truncated
    output. Returns None when the output has no recognizable pytest markers.
    """
    combined = "\n".join(
        part for part in (getattr(result, "stdout", None), getattr(result, "stderr", None)) if part
    )
    failed_lines: list[str] = []
    summary_lines: list[str] = []
    for line in combined.splitlines():
        stripped = line.strip()
        if stripped.startswith("FAILED "):
            failed_lines.append(stripped[len("FAILED "):].strip())
        else:
            undecorated = re.sub(r"^=+\s*|\s*=+$", "", stripped)
            if _PYTEST_SUMMARY_LINE_RE.search(undecorated) and " in " in undecorated:
                summary_lines.append(undecorated)
    if not failed_lines and not summary_lines:
        return None
    parts = []
    if failed_lines:
        parts.append("Failing tests:")
        parts.extend(f"- {_truncate_diagnostic(item, 240)}" for item in failed_lines[:8])
    if summary_lines:
        parts.append("Summary: " + _truncate_diagnostic(summary_lines[-1], 240))
    return "\n".join(parts)


def _tail_diagnostic(text: str, limit: int = 500) -> str:
    """Diagnostic window from the *tail* of the output.

    Pytest failure details (short test summary, assertion reasons) appear at
    the end of the output, so a tail window is far more informative than the
    head window for verification repair context.
    """
    normalized = text.replace("\r\n", "\n")
    if len(normalized) <= limit:
        return normalized.replace("\n", "\\n")
    window = normalized[-limit:].replace("\n", "\\n")
    return f"...[truncated] {window}"


def _truncate_diagnostic(text: str, limit: int = 500) -> str:
    normalized = text.replace("\r\n", "\n").replace("\n", "\\n")
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}...[truncated]"
