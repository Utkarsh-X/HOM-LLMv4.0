import json
import shutil
import sys
from inspect import Parameter, signature
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from homllm_v4.adapters.v3_provider_factory import build_v3_provider_edit_adapter_from_params
from homllm_v4.adapters.v3_provider_patch_factory import build_v3_provider_proposed_patch_planner
from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.command import CommandPolicy, CommandRunRequest
from homllm_v4.contracts.evaluation import CaseExecutionResult, EvaluationCase, EvaluationRunResult
from homllm_v4.evaluation.harness import V4EvaluationHarness
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.planning.direct_provider_patch_planner import DirectProviderPatchPlanner
from homllm_v4.planning.provider_edit_proposer import ProviderBackedEditProposer
from homllm_v4.planning.provider_edit_proposer import (
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
)
from homllm_v4.planning.provider_patch_planner import ProviderProposedPatchPlanRequest
from homllm_v4.runtime.provider_write_verify_runner import (
    ProviderWriteVerifyRunner,
    ProviderWriteVerifyRunRequest,
)
from homllm_v4.runtime.write_verify_loop import WriteVerifyLoop
from homllm_v4.services.command_service import LocalCommandService
from homllm_v4.services.direct_read_service import DirectReadService
from homllm_v4.services.patch_service import WorkspacePatchService


@dataclass(frozen=True)
class RealIndexProviderPatchCase:
    case_id: str
    target_file: str
    query: str
    intent: str
    expected_behavior: str
    provider_mode: str = "noop"
    verification_mode: str = "compile"
    planner_target_file: str | None = ""


REAL_INDEX_PROVIDER_PATCH_CASES = (
    RealIndexProviderPatchCase(
        case_id="admin-routes-noop",
        target_file="api/routes.py",
        query="admin_search_endpoint in api routes",
        intent="Validate a provider-proposed bounded no-op edit for admin search routing.",
        expected_behavior="api/routes.py remains syntactically valid after patch execution.",
    ),
    RealIndexProviderPatchCase(
        case_id="cache-manager-noop",
        target_file="cache/cache_manager.py",
        query="multi level cache miss fallback",
        intent="Validate a provider-proposed bounded no-op edit for cache fallback logic.",
        expected_behavior="cache/cache_manager.py remains syntactically valid after patch execution.",
    ),
    RealIndexProviderPatchCase(
        case_id="metrics-noop",
        target_file="monitoring/metrics.py",
        query="metrics collector counters gauges histograms",
        intent="Validate a provider-proposed bounded no-op edit for metrics aggregation.",
        expected_behavior="monitoring/metrics.py remains syntactically valid after patch execution.",
    ),
    RealIndexProviderPatchCase(
        case_id="string-truncate-guard",
        target_file="utils/string_tools.py",
        query="truncate_string max_length shorter than suffix edge case",
        intent=(
            "Fix truncate_string so max_length shorter than suffix never returns "
            "a string longer than max_length."
        ),
        expected_behavior=(
            "truncate_string('abcdef', 2) returns 'ab' and "
            "truncate_string('abcdef', 4) returns 'a...'."
        ),
        provider_mode="truncate_guard",
        verification_mode="truncate_guard",
    ),
    RealIndexProviderPatchCase(
        case_id="validate-file-path-drive-guard",
        target_file="utils/validators.py",
        query="validate_file_path rejects Windows drive absolute paths",
        intent="Reject Windows drive-qualified paths in validate_file_path.",
        expected_behavior="validate_file_path('C:/secret.txt') returns invalid.",
        provider_mode="file_path_drive_guard",
        verification_mode="file_path_drive_guard",
    ),
    RealIndexProviderPatchCase(
        case_id="validate-email-local-dot-guard",
        target_file="utils/validators.py",
        query="validate_email rejects consecutive dots in local part",
        intent="Reject email addresses with consecutive dots before @.",
        expected_behavior=(
            "validate_email('a..b@example.com') returns invalid while "
            "validate_email('a.b@example.com') remains valid."
        ),
        provider_mode="email_local_dot_guard",
        verification_mode="email_local_dot_guard",
    ),
    RealIndexProviderPatchCase(
        case_id="string-truncate-guard-target-selection",
        target_file="utils/string_tools.py",
        query="utils string_tools truncate_string max_length suffix guard",
        intent=(
            "Fix truncate_string so max_length shorter than suffix never returns "
            "a string longer than max_length."
        ),
        expected_behavior=(
            "truncate_string('abcdef', 2) returns 'ab' and "
            "truncate_string('abcdef', 4) returns 'a...'."
        ),
        provider_mode="truncate_guard",
        verification_mode="truncate_guard",
        planner_target_file=None,
    ),
    RealIndexProviderPatchCase(
        case_id="validate-file-path-drive-guard-target-selection",
        target_file="utils/validators.py",
        query="utils validators validate_file_path Windows drive absolute path rejection",
        intent="Reject Windows drive-qualified paths in validate_file_path.",
        expected_behavior="validate_file_path('C:/secret.txt') returns invalid.",
        provider_mode="file_path_drive_guard",
        verification_mode="file_path_drive_guard",
        planner_target_file=None,
    ),
    RealIndexProviderPatchCase(
        case_id="validate-email-local-dot-guard-target-selection",
        target_file="utils/validators.py",
        query="utils validators validate_email consecutive dots local part rejection",
        intent="Reject email addresses with consecutive dots before @.",
        expected_behavior=(
            "validate_email('a..b@example.com') returns invalid while "
            "validate_email('a.b@example.com') remains valid."
        ),
        provider_mode="email_local_dot_guard",
        verification_mode="email_local_dot_guard",
        planner_target_file=None,
    ),
    RealIndexProviderPatchCase(
        case_id="parse-date-strip",
        target_file="utils/date_helpers.py",
        query="utils date_helpers parse_date strips surrounding whitespace",
        intent="Make parse_date tolerate leading and trailing whitespace before parsing.",
        expected_behavior=(
            "parse_date(' 2024-01-02 ') returns a datetime and parse_date('bad') returns None."
        ),
        provider_mode="parse_date_strip",
        verification_mode="parse_date_strip",
    ),
    RealIndexProviderPatchCase(
        case_id="job-queue-total-size-guard",
        target_file="async_jobs/job_queue.py",
        query="async_jobs job_queue max_queue_size counts total pending jobs",
        intent=(
            "Make JobQueue enforce max_queue_size using total queued jobs, "
            "not priority bucket count."
        ),
        expected_behavior=(
            "A queue with max_queue_size=2 rejects the third queued job without "
            "calling get_queue_size from inside the existing lock."
        ),
        provider_mode="job_queue_size_guard",
        verification_mode="job_queue_size_guard",
    ),
    RealIndexProviderPatchCase(
        case_id="parse-date-strip-target-selection",
        target_file="utils/date_helpers.py",
        query="utils date_helpers parse_date strip whitespace before datetime parsing",
        intent="Make parse_date tolerate leading and trailing whitespace before parsing.",
        expected_behavior=(
            "parse_date(' 2024-01-02 ') returns a datetime and parse_date('bad') returns None."
        ),
        provider_mode="parse_date_strip",
        verification_mode="parse_date_strip",
        planner_target_file=None,
    ),
    RealIndexProviderPatchCase(
        case_id="job-queue-total-size-guard-target-selection",
        target_file="async_jobs/job_queue.py",
        query="async_jobs job_queue enqueue max_queue_size total pending jobs guard",
        intent=(
            "Make JobQueue enforce max_queue_size using total queued jobs, "
            "not priority bucket count."
        ),
        expected_behavior=(
            "A queue with max_queue_size=2 rejects the third queued job without "
            "calling get_queue_size from inside the existing lock."
        ),
        provider_mode="job_queue_size_guard",
        verification_mode="job_queue_size_guard",
        planner_target_file=None,
    ),
    RealIndexProviderPatchCase(
        case_id="cache-namespace-invalidate-target-selection",
        target_file="cache/cache_manager.py",
        query="cache namespace invalidation clears all memory entries for a namespace",
        intent="Make namespace-wide cache invalidation clear all memory entries in that namespace.",
        expected_behavior=(
            "After setting two entries in a namespace, invalidate(namespace) makes both reads miss."
        ),
        provider_mode="cache_namespace_invalidation",
        verification_mode="cache_namespace_invalidation",
        planner_target_file=None,
    ),
    RealIndexProviderPatchCase(
        case_id="metrics-labelled-stats-target-selection",
        target_file="monitoring/metrics.py",
        query="labelled histogram timer stats appear in all metrics export",
        intent="Make get_all_metrics preserve labelled histogram and timer statistics.",
        expected_behavior=(
            "After recording labelled histogram and timer values, get_all_metrics reports "
            "count == 1 for both labelled metric keys."
        ),
        provider_mode="metrics_labelled_stats",
        verification_mode="metrics_labelled_stats",
        planner_target_file=None,
    ),
)


INVENTORY_PROVIDER_PATCH_CASES = (
    RealIndexProviderPatchCase(
        case_id="inventory-sku-strip-normalization",
        target_file="inventory/items.py",
        query="inventory item normalize_sku strips whitespace and uppercases",
        intent="Make SKU normalization ignore surrounding whitespace before uppercasing.",
        expected_behavior="normalize_sku(' sku-1 ') returns 'SKU-1'.",
        provider_mode="inventory_sku_strip_normalization",
        verification_mode="inventory_sku_strip_normalization",
    ),
    RealIndexProviderPatchCase(
        case_id="pricing-negative-discount-guard",
        target_file="pricing/discounts.py",
        query="pricing discount negative rate should not produce negative discount",
        intent="Make negative discount rates produce a zero discount.",
        expected_behavior=(
            "calculate_discount(100, -0.2) returns 0.0 while "
            "calculate_discount(100, 0.2) returns 20.0."
        ),
        provider_mode="pricing_negative_discount_guard",
        verification_mode="pricing_negative_discount_guard",
    ),
    RealIndexProviderPatchCase(
        case_id="inventory-sku-strip-normalization-target-selection",
        target_file="inventory/items.py",
        query="inventory items normalize_sku strip surrounding whitespace before uppercase",
        intent="Make SKU normalization ignore surrounding whitespace before uppercasing.",
        expected_behavior="normalize_sku(' sku-1 ') returns 'SKU-1'.",
        provider_mode="inventory_sku_strip_normalization",
        verification_mode="inventory_sku_strip_normalization",
        planner_target_file=None,
    ),
    RealIndexProviderPatchCase(
        case_id="order-fulfillment-noop",
        target_file="orders/fulfillment.py",
        query="orders fulfillment_status cancelled shipped pending",
        intent="Validate a provider-proposed bounded no-op edit for order fulfillment status.",
        expected_behavior="orders/fulfillment.py remains syntactically valid after patch execution.",
    ),
)


REAL_INDEX_PROVIDER_PATCH_SUITES = {
    "core": REAL_INDEX_PROVIDER_PATCH_CASES,
    "inventory": INVENTORY_PROVIDER_PATCH_CASES,
}


def real_index_provider_patch_case_metadata(
    *, case_suite: str = "core"
) -> tuple[dict[str, object], ...]:
    cases = _select_suite_cases(case_suite)
    return tuple(
        {
            "case_id": case.case_id,
            "case_suite": case_suite,
            "target_file": case.target_file,
            "query": case.query,
            "provider_mode": case.provider_mode,
            "verification_mode": case.verification_mode,
            "planner_target_file": _case_planner_target_file(case),
        }
        for case in cases
    )


def run_real_index_provider_patch_suite(
    *,
    config_path: Path,
    source_workspace_root: Path,
    workspace_root: Path,
    artifact_root: Path,
    run_id: str | None = None,
    smoke_safe: bool = True,
    planner_builder=build_v3_provider_proposed_patch_planner,
    edit_provider_mode: str = "fake",
    live_provider_name: str = "gemini",
    live_model: str = "gemini-2.5-flash",
    live_max_output_tokens: int = 2048,
    live_api_key: str | None = None,
    live_provider_builder=build_v3_provider_edit_adapter_from_params,
    case_ids: tuple[str, ...] | None = None,
    max_prompt_chars: int | None = None,
    provider_repair_attempts: int = 0,
    planner_context_mode: str = "retrieval",
    direct_provider_target_source: str = "actual",
    case_suite: str = "core",
) -> EvaluationRunResult:
    resolved_run_id = run_id or str(uuid4())
    config_path = Path(config_path).resolve()
    source_workspace_root = Path(source_workspace_root).resolve()
    workspace_root = Path(workspace_root).resolve()
    artifact_root = Path(artifact_root).resolve()
    cases = tuple(
        _evaluation_case(case) for case in _select_cases(case_ids, case_suite=case_suite)
    )
    _validate_provider_mode(
        edit_provider_mode=edit_provider_mode,
        live_api_key=live_api_key,
    )
    normalized_planner_context_mode = _normalize_planner_context_mode(planner_context_mode)
    normalized_direct_provider_target_source = _normalize_direct_provider_target_source(
        direct_provider_target_source
    )
    artifact_manager = ArtifactManager(
        workspace_root=workspace_root,
        artifact_root=artifact_root,
    )
    artifact_manager.create_run(
        resolved_run_id,
        {
            "entrypoint": "homllm_v4.evaluation.real_index_provider_suites.run_real_index_provider_patch_suite",
            "source_workspace_root": str(source_workspace_root),
            "case_suite": case_suite,
            "case_count": len(cases),
        },
    )
    loop = WriteVerifyLoop(
        patch_service=WorkspacePatchService(),
        command_service=LocalCommandService(
            policy=CommandPolicy(
                allowed_executables=(Path(sys.executable).name,),
                default_timeout_seconds=15,
                max_timeout_seconds=15,
            )
        ),
        artifact_manager=artifact_manager,
        event_writer=EventWriter(artifact_root / resolved_run_id / "events.jsonl"),
    )

    def run_case(case: EvaluationCase) -> CaseExecutionResult:
        payload = case.input_payload
        target_file = str(payload["target_file"])
        case_workspace = _copy_case_workspace(
            source_workspace_root=source_workspace_root,
            workspace_root=workspace_root,
            run_id=resolved_run_id,
            case_id=case.case_id,
        )
        target_content = (case_workspace / target_file).read_text(encoding="utf-8")
        try:
            provider = _build_edit_provider(
                case=case,
                target_file=target_file,
                target_content=target_content,
                edit_provider_mode=edit_provider_mode,
                live_provider_name=live_provider_name,
                live_model=live_model,
                live_max_output_tokens=live_max_output_tokens,
                live_api_key=live_api_key,
                live_provider_builder=live_provider_builder,
            )
        except Exception as exc:
            return _provider_runtime_failure_result(
                case,
                exc,
                planner_context_mode=normalized_planner_context_mode,
                direct_provider_target_source=normalized_direct_provider_target_source,
            )
        try:
            planner = _build_planner(
                planner_builder=planner_builder,
                config_path=config_path,
                workspace_root=case_workspace,
                edit_provider=provider,
                smoke_safe=smoke_safe,
                artifact_manager=artifact_manager,
                max_prompt_chars=max_prompt_chars,
                planner_context_mode=normalized_planner_context_mode,
            )
        except Exception as exc:
            return _provider_runtime_failure_result(
                case,
                exc,
                planner_context_mode=normalized_planner_context_mode,
                direct_provider_target_source=normalized_direct_provider_target_source,
            )
        verification_argv = _verification_argv(case, target_file)
        planner_target_file = _evaluation_planner_target_file(case)
        if normalized_planner_context_mode == "direct_provider":
            planner_target_file = _direct_provider_target_file(
                case,
                actual_target_file=target_file,
                target_source=normalized_direct_provider_target_source,
            )
        try:
            result = ProviderWriteVerifyRunner(
                planner=planner,
                write_verify_loop=loop,
            ).run(
                ProviderWriteVerifyRunRequest(
                    task_id=case.case_id,
                    run_id=resolved_run_id,
                    workspace_root=str(case_workspace),
                    plan_request=ProviderProposedPatchPlanRequest(
                        task_id=case.case_id,
                        workspace_root=str(case_workspace),
                        query=str(payload["query"]),
                        task_class=case.task_type,
                        index_id=f"{case.case_id}:real-index",
                        target_file=planner_target_file,
                        intent=str(payload["intent"]),
                        expected_behavior=str(payload["expected_behavior"]),
                        verification_argv=verification_argv,
                        retrieval_policy={"intent": "PATCH", "top_k": 20},
                    ),
                    max_verification_commands=1,
                    provider_repair_attempts=provider_repair_attempts,
                    rollback_on_failure=True,
                )
            )
        except Exception as exc:
            return _provider_runtime_failure_result(
                case,
                exc,
                planner_context_mode=normalized_planner_context_mode,
                direct_provider_target_source=normalized_direct_provider_target_source,
            )

        return _case_result(
            stop_reason=result.stop_reason,
            error_code=result.error_code,
            verification_results=result.verification_results,
            patch_attempt_count=result.patch_attempt_count,
            planner_metrics=result.planner_metrics,
            case_metrics=_case_quality_metrics(
                case,
                planner_context_mode=normalized_planner_context_mode,
                direct_provider_target_source=normalized_direct_provider_target_source,
            ),
        )

    def run_baseline(case: EvaluationCase) -> CaseExecutionResult:
        return _run_no_patch_baseline(
            case=case,
            source_workspace_root=source_workspace_root,
            workspace_root=workspace_root,
            run_id=resolved_run_id,
            command_service=loop.command_service,
        )

    harness = V4EvaluationHarness(
        artifact_manager=artifact_manager,
        runners={
            "real_index_provider_write_verify": run_case,
            "no_patch_baseline": run_baseline,
        },
    )
    return harness.run(run_id=resolved_run_id, cases=cases)


def _evaluation_case(case: RealIndexProviderPatchCase) -> EvaluationCase:
    return EvaluationCase(
        case_id=case.case_id,
        runner_id="real_index_provider_write_verify",
        task_type="real_index_provider_patch",
        input_payload={
            "target_file": case.target_file,
            "query": case.query,
            "intent": case.intent,
            "expected_behavior": case.expected_behavior,
            "provider_mode": case.provider_mode,
            "verification_mode": case.verification_mode,
            "planner_target_file": _case_planner_target_file(case),
        },
        expected_stop_reason="verified",
        baseline_runner_id=(
            "no_patch_baseline" if case.verification_mode != "compile" else None
        ),
    )


def _select_suite_cases(case_suite: str) -> tuple[RealIndexProviderPatchCase, ...]:
    try:
        return REAL_INDEX_PROVIDER_PATCH_SUITES[case_suite]
    except KeyError as exc:
        raise ValueError(f"unknown_case_suite: {case_suite}") from exc


def _select_cases(
    case_ids: tuple[str, ...] | None,
    *,
    case_suite: str = "core",
) -> tuple[RealIndexProviderPatchCase, ...]:
    suite_cases = _select_suite_cases(case_suite)
    if case_ids is None:
        return suite_cases

    available = {case.case_id for case in suite_cases}
    requested = set(case_ids)
    unknown = tuple(sorted(requested - available))
    if unknown:
        raise ValueError(f"unknown_case_ids: {', '.join(unknown)}")

    selected = tuple(case for case in suite_cases if case.case_id in requested)
    if not selected:
        raise ValueError("no_case_ids_selected")
    return selected


def _case_planner_target_file(case: RealIndexProviderPatchCase) -> str | None:
    if case.planner_target_file == "":
        return case.target_file
    return case.planner_target_file


def _evaluation_planner_target_file(case: EvaluationCase) -> str | None:
    value = case.input_payload.get("planner_target_file")
    if isinstance(value, str):
        return value
    return None


def _validate_provider_mode(*, edit_provider_mode: str, live_api_key: str | None) -> None:
    if edit_provider_mode == "fake":
        return
    if edit_provider_mode == "live":
        if not live_api_key:
            raise ValueError("live_provider_api_key_required")
        return
    raise ValueError(f"unsupported edit_provider_mode: {edit_provider_mode}")


def _normalize_planner_context_mode(value: str) -> str:
    normalized = value.replace("-", "_")
    if normalized in {"retrieval", "direct_provider"}:
        return normalized
    raise ValueError(f"unsupported_planner_context_mode: {value}")


def _normalize_direct_provider_target_source(value: str) -> str:
    normalized = value.replace("-", "_")
    if normalized in {"actual", "planner"}:
        return normalized
    raise ValueError(f"unsupported_direct_provider_target_source: {value}")


def _direct_provider_target_file(
    case: EvaluationCase,
    *,
    actual_target_file: str,
    target_source: str,
) -> str | None:
    if target_source == "actual":
        return actual_target_file
    return _evaluation_planner_target_file(case)


def _copy_case_workspace(
    *,
    source_workspace_root: Path,
    workspace_root: Path,
    run_id: str,
    case_id: str,
) -> Path:
    target = workspace_root / run_id / "cases" / case_id
    if target.exists():
        raise ValueError(f"case_workspace_exists: {target}")
    shutil.copytree(source_workspace_root, target, ignore=_ignore_workspace_copy_artifacts)
    return target


def _copy_baseline_workspace(
    *,
    source_workspace_root: Path,
    workspace_root: Path,
    run_id: str,
    case_id: str,
) -> Path:
    target = workspace_root / run_id / "baselines" / case_id
    if target.exists():
        raise ValueError(f"baseline_workspace_exists: {target}")
    shutil.copytree(source_workspace_root, target, ignore=_ignore_workspace_copy_artifacts)
    return target


def _ignore_workspace_copy_artifacts(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name == "__pycache__" or name.endswith((".pyc", ".pyo"))
    }


def _build_edit_provider(
    *,
    case: EvaluationCase,
    target_file: str,
    target_content: str,
    edit_provider_mode: str,
    live_provider_name: str,
    live_model: str,
    live_max_output_tokens: int,
    live_api_key: str | None,
    live_provider_builder,
):
    if edit_provider_mode == "fake":
        return _PromptAwareNoopProvider(
            target_file=target_file,
            new_content=_provider_content(case, target_content),
        )
    if edit_provider_mode == "live":
        return live_provider_builder(
            provider_name=live_provider_name,
            model=live_model,
            api_key=live_api_key,
            temperature=0.0,
            max_output_tokens=live_max_output_tokens,
        )
    raise ValueError(f"unsupported edit_provider_mode: {edit_provider_mode}")


def _build_planner(
    *,
    planner_builder,
    config_path: Path,
    workspace_root: Path,
    edit_provider,
    smoke_safe: bool,
    artifact_manager: ArtifactManager,
    max_prompt_chars: int | None,
    planner_context_mode: str,
):
    if planner_context_mode == "direct_provider":
        return DirectProviderPatchPlanner(
            direct_read_service=DirectReadService(workspace_root=workspace_root),
            edit_proposer=ProviderBackedEditProposer(
                provider=edit_provider,
                artifact_manager=artifact_manager,
                max_prompt_chars=max_prompt_chars,
            ),
        )
    kwargs = {
        "config_path": config_path,
        "workspace_root": workspace_root,
        "edit_provider": edit_provider,
        "smoke_safe": smoke_safe,
    }
    if _accepts_keyword(planner_builder, "artifact_manager"):
        kwargs["artifact_manager"] = artifact_manager
    if _accepts_keyword(planner_builder, "max_prompt_chars"):
        kwargs["max_prompt_chars"] = max_prompt_chars
    return planner_builder(**kwargs)


def _accepts_keyword(callable_object, keyword: str) -> bool:
    parameters = signature(callable_object).parameters.values()
    return any(
        parameter.kind is Parameter.VAR_KEYWORD or parameter.name == keyword
        for parameter in parameters
    )


def _provider_content(case: EvaluationCase, target_content: str) -> str:
    if case.input_payload.get("provider_mode") == "truncate_guard":
        old = (
            "    if len(text) <= max_length:\n"
            "        return text\n"
            "    return text[:max_length - len(suffix)] + suffix"
        )
        new = (
            "    if len(text) <= max_length:\n"
            "        return text\n"
            "    if max_length <= len(suffix):\n"
            "        return text[:max_length]\n"
            "    return text[:max_length - len(suffix)] + suffix"
        )
        if old not in target_content:
            raise ValueError("truncate_guard_pattern_not_found")
        return target_content.replace(old, new)
    if case.input_payload.get("provider_mode") == "file_path_drive_guard":
        old = (
            "    if '..' in file_path or file_path.startswith('/'):\n"
            "        return False, \"Invalid file path\""
        )
        new = (
            "    if '..' in file_path or file_path.startswith('/') "
            "or file_path.startswith('\\\\') or ':' in file_path:\n"
            "        return False, \"Invalid file path\""
        )
        if old not in target_content:
            raise ValueError("file_path_drive_guard_pattern_not_found")
        return target_content.replace(old, new)
    if case.input_payload.get("provider_mode") == "email_local_dot_guard":
        old = (
            "    if not re.match(email_pattern, email):\n"
            "        return False, \"Invalid email format\"\n"
            "    \n"
            "    return True, None"
        )
        new = (
            "    if not re.match(email_pattern, email):\n"
            "        return False, \"Invalid email format\"\n"
            "    \n"
            "    local_part = email.split('@', 1)[0]\n"
            "    if '..' in local_part:\n"
            "        return False, \"Invalid email format\"\n"
            "    \n"
            "    return True, None"
        )
        if old not in target_content:
            raise ValueError("email_local_dot_guard_pattern_not_found")
        return target_content.replace(old, new)
    if case.input_payload.get("provider_mode") == "parse_date_strip":
        old = "        return datetime.strptime(date_string, format_str)"
        new = "        return datetime.strptime(date_string.strip(), format_str)"
        if old not in target_content:
            raise ValueError("parse_date_strip_pattern_not_found")
        return target_content.replace(old, new)
    if case.input_payload.get("provider_mode") == "job_queue_size_guard":
        old = (
            "            if len(self.pending_jobs) >= self.max_queue_size:\n"
            "                raise RuntimeError(f\"Queue full (max {self.max_queue_size})\")"
        )
        new = (
            "            current_queue_size = sum(len(jobs) for jobs in self.pending_jobs.values())\n"
            "            if current_queue_size >= self.max_queue_size:\n"
            "                raise RuntimeError(f\"Queue full (max {self.max_queue_size})\")"
        )
        if old not in target_content:
            raise ValueError("job_queue_size_guard_pattern_not_found")
        return target_content.replace(old, new)
    if case.input_payload.get("provider_mode") == "cache_namespace_invalidation":
        old = "        return hashlib.md5(key.encode()).hexdigest()"
        new = "        return key"
        if old not in target_content:
            raise ValueError("cache_namespace_invalidation_pattern_not_found")
        return target_content.replace(old, new)
    if case.input_payload.get("provider_mode") == "metrics_labelled_stats":
        old = (
            "    def get_all_metrics(self) -> Dict[str, Any]:\n"
            "        \"\"\"Get all collected metrics.\"\"\"\n"
            "        return {\n"
            "            \"counters\": dict(self.counters),\n"
            "            \"gauges\": dict(self.gauges),\n"
            "            \"histogram_stats\": {\n"
            "                key: self.get_histogram_stats(key.split(\"{\")[0])\n"
            "                for key in self.histograms.keys()\n"
            "            },\n"
            "            \"timer_stats\": {\n"
            "                key: self.get_timer_stats(key.split(\"{\")[0])\n"
            "                for key in self.timers.keys()\n"
            "            }\n"
            "        }"
        )
        new = (
            "    def get_all_metrics(self) -> Dict[str, Any]:\n"
            "        \"\"\"Get all collected metrics.\"\"\"\n"
            "        def value_stats(values: List[float]) -> Dict[str, float]:\n"
            "            if not values:\n"
            "                return {}\n"
            "            sorted_values = sorted(values)\n"
            "            return {\n"
            "                \"count\": len(values),\n"
            "                \"sum\": sum(values),\n"
            "                \"mean\": sum(values) / len(values),\n"
            "                \"min\": min(values),\n"
            "                \"max\": max(values),\n"
            "                \"p50\": sorted_values[len(values) // 2],\n"
            "                \"p95\": sorted_values[int(len(values) * 0.95)],\n"
            "                \"p99\": sorted_values[int(len(values) * 0.99)]\n"
            "            }\n"
            "        return {\n"
            "            \"counters\": dict(self.counters),\n"
            "            \"gauges\": dict(self.gauges),\n"
            "            \"histogram_stats\": {\n"
            "                key: value_stats(values)\n"
            "                for key, values in self.histograms.items()\n"
            "            },\n"
            "            \"timer_stats\": {\n"
            "                key: value_stats(values)\n"
            "                for key, values in self.timers.items()\n"
            "            }\n"
            "        }"
        )
        if old not in target_content:
            raise ValueError("metrics_labelled_stats_pattern_not_found")
        return target_content.replace(old, new)
    if case.input_payload.get("provider_mode") == "inventory_sku_strip_normalization":
        old = "    return sku.upper()"
        new = "    return sku.strip().upper()"
        if old not in target_content:
            raise ValueError("inventory_sku_strip_normalization_pattern_not_found")
        return target_content.replace(old, new)
    if case.input_payload.get("provider_mode") == "pricing_negative_discount_guard":
        old = "    return price * rate"
        new = (
            "    if rate < 0:\n"
            "        return 0.0\n"
            "    return price * rate"
        )
        if old not in target_content:
            raise ValueError("pricing_negative_discount_guard_pattern_not_found")
        return target_content.replace(old, new)
    return target_content


def _verification_argv(case: EvaluationCase, target_file: str) -> tuple[str, ...]:
    if case.input_payload.get("verification_mode") == "truncate_guard":
        return (
            sys.executable,
            "-c",
            "from utils.string_tools import truncate_string; "
            "raise SystemExit(0 if truncate_string('abcdef', 2) == 'ab' "
            "and truncate_string('abcdef', 4) == 'a...' else 1)",
        )
    if case.input_payload.get("verification_mode") == "file_path_drive_guard":
        return (
            sys.executable,
            "-c",
            "from utils.validators import validate_file_path; "
            "raise SystemExit(0 if not validate_file_path('C:/secret.txt')[0] "
            "and not validate_file_path('\\\\secret.txt')[0] else 1)",
        )
    if case.input_payload.get("verification_mode") == "email_local_dot_guard":
        return (
            sys.executable,
            "-c",
            "from utils.validators import validate_email; "
            "raise SystemExit(0 if not validate_email('a..b@example.com')[0] "
            "and validate_email('a.b@example.com')[0] else 1)",
        )
    if case.input_payload.get("verification_mode") == "parse_date_strip":
        return (
            sys.executable,
            "-c",
            "from utils.date_helpers import parse_date; "
            "raise SystemExit(0 if parse_date(' 2024-01-02 ') is not None "
            "and parse_date('bad') is None else 1)",
        )
    if case.input_payload.get("verification_mode") == "job_queue_size_guard":
        return (
            sys.executable,
            "-c",
            "from async_jobs.job_queue import JobQueue; "
            "JobQueue._instance = None; q = JobQueue(); q.max_queue_size = 2; "
            "q.enqueue('a', {}); q.enqueue('b', {}); ok = False\n"
            "try:\n"
            "    q.enqueue('c', {})\n"
            "except RuntimeError:\n"
            "    ok = True\n"
            "raise SystemExit(0 if ok else 1)",
        )
    if case.input_payload.get("verification_mode") == "cache_namespace_invalidation":
        return (
            sys.executable,
            "-c",
            "import sys, types; "
            "sys.modules['redis'] = types.SimpleNamespace("
            "ConnectionPool=lambda **kwargs: None, Redis=lambda connection_pool: None); "
            "from cache.cache_manager import CacheManager; "
            "CacheManager._instance = None; cm = CacheManager(); cm.redis = None; "
            "cm.set('users', 'a', 1); cm.set('users', 'b', 2); "
            "cm.invalidate('users'); "
            "raise SystemExit(0 if cm.get('users', 'a') is None "
            "and cm.get('users', 'b') is None else 1)",
        )
    if case.input_payload.get("verification_mode") == "metrics_labelled_stats":
        return (
            sys.executable,
            "-c",
            "from monitoring.metrics import MetricsCollector; "
            "MetricsCollector._instance = None; m = MetricsCollector(); "
            "m.record_histogram('latency', 12.0, labels={'route': 'search'}); "
            "m.record_timer('latency', 8.0, labels={'route': 'search'}); "
            "all_metrics = m.get_all_metrics(); "
            "ok = all_metrics['histogram_stats']['latency{route=search}']['count'] == 1 "
            "and all_metrics['timer_stats']['latency{route=search}']['count'] == 1; "
            "raise SystemExit(0 if ok else 1)",
        )
    if case.input_payload.get("verification_mode") == "inventory_sku_strip_normalization":
        return (
            sys.executable,
            "-c",
            "from inventory.items import normalize_sku; "
            "raise SystemExit(0 if normalize_sku(' sku-1 ') == 'SKU-1' else 1)",
        )
    if case.input_payload.get("verification_mode") == "pricing_negative_discount_guard":
        return (
            sys.executable,
            "-c",
            "from pricing.discounts import calculate_discount; "
            "ok = calculate_discount(100, -0.2) == 0.0 "
            "and calculate_discount(100, 0.2) == 20.0; "
            "raise SystemExit(0 if ok else 1)",
        )
    return (sys.executable, "-m", "compileall", "-q", target_file)


def _run_no_patch_baseline(
    *,
    case: EvaluationCase,
    source_workspace_root: Path,
    workspace_root: Path,
    run_id: str,
    command_service: LocalCommandService,
) -> CaseExecutionResult:
    target_file = str(case.input_payload["target_file"])
    baseline_workspace = _copy_baseline_workspace(
        source_workspace_root=source_workspace_root,
        workspace_root=workspace_root,
        run_id=run_id,
        case_id=case.case_id,
    )
    command_result = command_service.run(
        CommandRunRequest(
            task_id=f"{case.case_id}:baseline",
            workspace_root=str(baseline_workspace),
            cwd=".",
            argv=_verification_argv(case, target_file),
            timeout_seconds=15,
        )
    )
    if not command_result.ok or command_result.output is None:
        return CaseExecutionResult(
            stop_reason="verification_failed",
            metrics={
                "verification_count": 0,
                "verification_duration_ms": 0,
                "verification_output_chars": 0,
                "verification_output_token_estimate": 0,
            },
            error_code=command_result.error.code if command_result.error else "command_failed",
        )

    output = command_result.output
    output_chars = len(output.stdout or "") + len(output.stderr or "")
    verified = output.exit_code == 0 and not output.timed_out and not output.denied
    return CaseExecutionResult(
        stop_reason="verified" if verified else "verification_failed",
        metrics={
            "verification_count": 1,
            "verification_duration_ms": int(output.duration_ms),
            "verification_output_chars": output_chars,
            "verification_output_token_estimate": output_chars // 4,
        },
        error_code=None,
    )


def _case_result(
    *,
    stop_reason: str,
    error_code: str | None,
    verification_results,
    patch_attempt_count: int,
    planner_metrics: dict[str, object] | None = None,
    case_metrics: dict[str, object] | None = None,
) -> CaseExecutionResult:
    output_chars = sum(
        len(command.stdout or "") + len(command.stderr or "")
        for command in verification_results
    )
    metrics = {
        "patch_attempt_count": patch_attempt_count,
        "verification_count": len(verification_results),
        "verification_duration_ms": sum(
            int(command.duration_ms) for command in verification_results
        ),
        "verification_output_chars": output_chars,
        "verification_output_token_estimate": output_chars // 4,
        "provider_tokens_in": 0,
        "provider_tokens_out": 0,
    }
    metrics.update(planner_metrics or {})
    metrics.update(case_metrics or {})
    return CaseExecutionResult(
        stop_reason=stop_reason,
        error_code=error_code,
        metrics=metrics,
    )


def _provider_runtime_failure_result(
    case: EvaluationCase,
    exc: Exception,
    *,
    planner_context_mode: str,
    direct_provider_target_source: str,
) -> CaseExecutionResult:
    return _case_result(
        stop_reason="patch_failed",
        error_code="provider_invocation_failed",
        verification_results=(),
        patch_attempt_count=0,
        planner_metrics={"provider_runtime_exception_type": type(exc).__name__},
        case_metrics=_case_quality_metrics(
            case,
            planner_context_mode=planner_context_mode,
            direct_provider_target_source=direct_provider_target_source,
        ),
    )


def _case_quality_metrics(
    case: EvaluationCase,
    *,
    planner_context_mode: str,
    direct_provider_target_source: str,
) -> dict[str, object]:
    verification_mode = str(case.input_payload.get("verification_mode", "compile"))
    if planner_context_mode == "direct_provider":
        baseline_target_knowledge = (
            "target_known"
            if direct_provider_target_source == "actual"
            else "target_unavailable"
        )
    else:
        baseline_target_knowledge = "retrieval_localizes"
    return {
        "quality_requires_localization": _evaluation_planner_target_file(case) is None,
        "quality_verification_kind": (
            "compile" if verification_mode == "compile" else "behavior"
        ),
        "quality_provider_mode": str(case.input_payload.get("provider_mode", "unknown")),
        "quality_verification_mode": verification_mode,
        "quality_baseline_target_knowledge": baseline_target_knowledge,
    }


class _PromptAwareNoopProvider:
    tokens_in = 1
    tokens_out = 1

    def __init__(self, *, target_file: str, new_content: str) -> None:
        self.target_file = target_file
        self.new_content = new_content

    def propose_edit(self, request: ProviderEditProposalRequest) -> ProviderEditProposalResponse:
        evidence_ids = ()
        for line in request.prompt.splitlines():
            if line.startswith("Evidence IDs:"):
                evidence_ids = tuple(
                    item.strip()
                    for item in line.removeprefix("Evidence IDs:").split(",")
                    if item.strip()
                )
                break
        return ProviderEditProposalResponse(
            text=json.dumps(
                {
                    "target_file": self.target_file,
                    "new_content": self.new_content,
                    "rationale": "No-op real-index benchmark proposal.",
                    "evidence_ids": list(evidence_ids),
                    "risk_flags": [],
                }
            ),
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            model="fake",
            metadata={"provider": "real-index-benchmark-fake"},
        )
