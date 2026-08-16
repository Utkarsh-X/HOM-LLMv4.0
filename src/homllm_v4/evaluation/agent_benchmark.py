import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.evaluation import EvaluationCaseResult, EvaluationRunResult
from homllm_v4.evaluation.canned_provider import PromptAwareCannedProvider
from homllm_v4.runtime.agent_run import HomllmAgentRunRequest, HomllmAgentRunResult
from homllm_v4.runtime.agent_run import run_homllm_agent


@dataclass(frozen=True)
class AgentBenchmarkCase:
    case_id: str
    query: str
    edit_intent: str
    expected_behavior: str
    target_file: str | None
    verification_argv: tuple[str, ...]
    expected_stop_reason: str = "verified"
    expected_error_code: str | None = None
    prepare_index: bool = True
    source_workspace_root: Path | None = None
    metadata: dict[str, object] | None = None


INTERNAL_AGENT_BENCHMARK_CASES = (
    AgentBenchmarkCase(
        case_id="admin-routes-compile",
        query="admin_search_endpoint in api routes",
        edit_intent="Validate a bounded no-op edit for admin search routing.",
        expected_behavior="api/routes.py remains syntactically valid after patch execution.",
        target_file="api/routes.py",
        verification_argv=(sys.executable, "-m", "compileall", "-q", "api/routes.py"),
        metadata={
            "verification_kind": "compile",
            "requires_localization": False,
            "provider_mode": "noop",
        },
    ),
    AgentBenchmarkCase(
        case_id="cache-manager-compile",
        query="multi level cache miss fallback",
        edit_intent="Validate a bounded no-op edit for cache fallback logic.",
        expected_behavior="cache/cache_manager.py remains syntactically valid after patch execution.",
        target_file="cache/cache_manager.py",
        verification_argv=(sys.executable, "-m", "compileall", "-q", "cache/cache_manager.py"),
        metadata={
            "verification_kind": "compile",
            "requires_localization": False,
            "provider_mode": "noop",
        },
    ),
    AgentBenchmarkCase(
        case_id="metrics-compile",
        query="metrics collector counters gauges histograms",
        edit_intent="Validate a bounded no-op edit for metrics aggregation.",
        expected_behavior="monitoring/metrics.py remains syntactically valid after patch execution.",
        target_file="monitoring/metrics.py",
        verification_argv=(sys.executable, "-m", "compileall", "-q", "monitoring/metrics.py"),
        metadata={
            "verification_kind": "compile",
            "requires_localization": False,
            "provider_mode": "noop",
        },
    ),
    AgentBenchmarkCase(
        case_id="string-truncate-guard",
        query="truncate_string max_length shorter than suffix edge case",
        edit_intent="Fix truncate_string so max_length shorter than suffix never returns a string longer than max_length.",
        expected_behavior="truncate_string('abcdef', 2) returns 'ab' and truncate_string('abcdef', 4) returns 'a...'.",
        target_file="utils/string_tools.py",
        verification_argv=(
            sys.executable,
            "-c",
            "from utils.string_tools import truncate_string; "
            "raise SystemExit(0 if truncate_string('abcdef', 2) == 'ab' "
            "and truncate_string('abcdef', 4) == 'a...' else 1)",
        ),
        metadata={
            "verification_kind": "behavior",
            "requires_localization": False,
            "provider_mode": "truncate_guard",
        },
    ),
    AgentBenchmarkCase(
        case_id="validate-file-path-drive-guard",
        query="validate_file_path rejects Windows drive absolute paths",
        edit_intent="Reject Windows drive-qualified paths in validate_file_path.",
        expected_behavior="validate_file_path('C:/secret.txt') returns invalid.",
        target_file="utils/validators.py",
        verification_argv=(
            sys.executable,
            "-c",
            "from utils.validators import validate_file_path; "
            "raise SystemExit(0 if not validate_file_path('C:/secret.txt')[0] else 1)",
        ),
        metadata={
            "verification_kind": "behavior",
            "requires_localization": False,
            "provider_mode": "file_path_drive_guard",
        },
    ),
    AgentBenchmarkCase(
        case_id="validate-email-local-dot-guard",
        query="validate_email rejects consecutive dots in local part",
        edit_intent="Reject email addresses with consecutive dots before @.",
        expected_behavior="validate_email('a..b@example.com') returns invalid while validate_email('a.b@example.com') remains valid.",
        target_file="utils/validators.py",
        verification_argv=(
            sys.executable,
            "-c",
            "from utils.validators import validate_email; "
            "raise SystemExit(0 if not validate_email('a..b@example.com')[0] "
            "and validate_email('a.b@example.com')[0] else 1)",
        ),
        metadata={
            "verification_kind": "behavior",
            "requires_localization": False,
            "provider_mode": "email_local_dot_guard",
        },
    ),
    AgentBenchmarkCase(
        case_id="string-truncate-target-selection",
        query="utils string_tools truncate_string max_length suffix guard",
        edit_intent="Fix truncate_string so max_length shorter than suffix never returns a string longer than max_length.",
        expected_behavior="truncate_string('abcdef', 2) returns 'ab' and truncate_string('abcdef', 4) returns 'a...'.",
        target_file=None,
        verification_argv=(
            sys.executable,
            "-c",
            "from utils.string_tools import truncate_string; "
            "raise SystemExit(0 if truncate_string('abcdef', 2) == 'ab' "
            "and truncate_string('abcdef', 4) == 'a...' else 1)",
        ),
        metadata={
            "verification_kind": "behavior",
            "requires_localization": True,
            "provider_mode": "truncate_guard",
        },
    ),
    AgentBenchmarkCase(
        case_id="parse-date-strip",
        query="utils date_helpers parse_date strips surrounding whitespace",
        edit_intent="Make parse_date tolerate leading and trailing whitespace before parsing.",
        expected_behavior="parse_date(' 2024-01-02 ') returns a datetime and parse_date('bad') returns None.",
        target_file="utils/date_helpers.py",
        verification_argv=(
            sys.executable,
            "-c",
            "from utils.date_helpers import parse_date; "
            "raise SystemExit(0 if parse_date(' 2024-01-02 ') is not None "
            "and parse_date('bad') is None else 1)",
        ),
        metadata={
            "verification_kind": "behavior",
            "requires_localization": False,
            "provider_mode": "parse_date_strip",
        },
    ),
    AgentBenchmarkCase(
        case_id="job-queue-total-size-guard",
        query="async_jobs job_queue max_queue_size counts total pending jobs",
        edit_intent="Make JobQueue enforce max_queue_size using total queued jobs, not priority bucket count.",
        expected_behavior="A queue with max_queue_size=2 rejects the third queued job.",
        target_file="async_jobs/job_queue.py",
        verification_argv=(
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
        ),
        metadata={
            "verification_kind": "behavior",
            "requires_localization": False,
            "provider_mode": "job_queue_size_guard",
        },
    ),
    AgentBenchmarkCase(
        case_id="parse-date-target-selection",
        query="utils date_helpers parse_date strip whitespace before datetime parsing",
        edit_intent="Make parse_date tolerate leading and trailing whitespace before parsing.",
        expected_behavior="parse_date(' 2024-01-02 ') returns a datetime and parse_date('bad') returns None.",
        target_file=None,
        verification_argv=(
            sys.executable,
            "-c",
            "from utils.date_helpers import parse_date; "
            "raise SystemExit(0 if parse_date(' 2024-01-02 ') is not None "
            "and parse_date('bad') is None else 1)",
        ),
        metadata={
            "verification_kind": "behavior",
            "requires_localization": True,
            "provider_mode": "parse_date_strip",
        },
    ),
    AgentBenchmarkCase(
        case_id="cache-namespace-invalidate",
        query="cache namespace invalidation clears all memory entries for a namespace",
        edit_intent="Make namespace-wide cache invalidation clear all memory entries in that namespace.",
        expected_behavior=(
            "After setting two entries in a namespace, invalidate(namespace) makes both reads miss."
        ),
        target_file="cache/cache_manager.py",
        verification_argv=(
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
        ),
        metadata={
            "verification_kind": "behavior",
            "requires_localization": False,
            "provider_mode": "cache_namespace_invalidation",
        },
    ),
    AgentBenchmarkCase(
        case_id="cache-namespace-invalidate-target-selection",
        query="cache namespace invalidation clears all memory entries for a namespace",
        edit_intent="Make namespace-wide cache invalidation clear all memory entries in that namespace.",
        expected_behavior=(
            "After setting two entries in a namespace, invalidate(namespace) makes both reads miss."
        ),
        target_file=None,
        verification_argv=(
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
        ),
        metadata={
            "verification_kind": "behavior",
            "requires_localization": True,
            "provider_mode": "cache_namespace_invalidation",
        },
    ),
    AgentBenchmarkCase(
        case_id="metrics-labelled-stats",
        query="labelled histogram timer stats appear in all metrics export",
        edit_intent="Make get_all_metrics preserve labelled histogram and timer statistics.",
        expected_behavior=(
            "After recording labelled histogram and timer values, get_all_metrics reports "
            "count == 1 for both labelled metric keys."
        ),
        target_file="monitoring/metrics.py",
        verification_argv=(
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
        ),
        metadata={
            "verification_kind": "behavior",
            "requires_localization": False,
            "provider_mode": "metrics_labelled_stats",
        },
    ),
    AgentBenchmarkCase(
        case_id="metrics-labelled-stats-target-selection",
        query="labelled histogram timer stats appear in all metrics export",
        edit_intent="Make get_all_metrics preserve labelled histogram and timer statistics.",
        expected_behavior=(
            "After recording labelled histogram and timer values, get_all_metrics reports "
            "count == 1 for both labelled metric keys."
        ),
        target_file=None,
        verification_argv=(
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
        ),
        metadata={
            "verification_kind": "behavior",
            "requires_localization": True,
            "provider_mode": "metrics_labelled_stats",
        },
    ),
    AgentBenchmarkCase(
        case_id="hashing-needs-rehash-hidden-test",
        query="security hashing needs_rehash flags legacy unsalted password hashes",
        edit_intent=(
            "Make needs_rehash return True for hashes that do not use the current "
            "salted (salt:hash) format so legacy unsalted hashes get upgraded."
        ),
        expected_behavior=(
            "needs_rehash returns True for unsalted or short-salt hashes and "
            "False for freshly hashed passwords."
        ),
        target_file="security/hashing.py",
        verification_argv=(
            sys.executable,
            "-m",
            "pytest",
            "tests/test_hashing.py",
            "-q",
        ),
        metadata={
            "verification_kind": "hidden_test",
            "requires_localization": False,
            "provider_mode": "hashing_needs_rehash",
        },
    ),
    AgentBenchmarkCase(
        case_id="filters-anonymous-public-hidden-test",
        query="search_engine filters anonymous users cannot see public files",
        edit_intent=(
            "Make PermissionFilter allow anonymous users (no user_id) to see "
            "public files while still blocking private files."
        ),
        expected_behavior=(
            "filter_by_permissions keeps public file paths even when the user dict "
            "has no user_id, and still drops private user files."
        ),
        target_file="search_engine/filters.py",
        verification_argv=(
            sys.executable,
            "-m",
            "pytest",
            "tests/test_filters.py",
            "-q",
        ),
        metadata={
            "verification_kind": "hidden_test",
            "requires_localization": False,
            "provider_mode": "filters_anonymous_public",
        },
    ),
    AgentBenchmarkCase(
        case_id="query-optimizer-pushdown-hidden-test",
        query="optimization query_optimizer predicate pushdown orders most selective filters first",
        edit_intent=(
            "Make predicate pushdown order filters from most selective "
            "(lowest selectivity value) to least selective."
        ),
        expected_behavior=(
            "After pushdown, an equality filter (selectivity 0.01) precedes a "
            "range filter (selectivity 0.1)."
        ),
        target_file="optimization/query_optimizer.py",
        verification_argv=(
            sys.executable,
            "-m",
            "pytest",
            "tests/test_query_optimizer.py",
            "-q",
        ),
        metadata={
            "verification_kind": "hidden_test",
            "requires_localization": False,
            "provider_mode": "query_optimizer_pushdown",
        },
    ),
    AgentBenchmarkCase(
        case_id="redis-pickle-hit-stats-hidden-test",
        query="cache redis_client pickle deserialization counts a cache hit as a hit",
        edit_intent=(
            "Make RedisClient.get count a successful pickle deserialization as a "
            "cache hit so hit/miss statistics are accurate."
        ),
        expected_behavior=(
            "After a pickle round-trip, get_stats reports hits == 1 and misses == 0."
        ),
        target_file="cache/redis_client.py",
        verification_argv=(
            sys.executable,
            "-m",
            "pytest",
            "tests/test_redis_client.py",
            "-q",
        ),
        metadata={
            "verification_kind": "hidden_test",
            "requires_localization": False,
            "provider_mode": "redis_pickle_hit_stats",
        },
    ),
    AgentBenchmarkCase(
        case_id="query-planner-parameter-aware-cache-hidden-test",
        query="optimization query_planner plan cache distinguishes queries by parameters",
        edit_intent=(
            "Make QueryPlanner include query parameters in the plan cache key so "
            "the same SQL text with different parameters produces distinct plans."
        ),
        expected_behavior=(
            "plan_query with different parameters returns different plan ids and "
            "records no cache hit for the second call."
        ),
        target_file="optimization/query_planner.py",
        verification_argv=(
            sys.executable,
            "-m",
            "pytest",
            "tests/test_query_planner.py",
            "-q",
        ),
        metadata={
            "verification_kind": "hidden_test",
            "requires_localization": False,
            "provider_mode": "query_planner_param_cache",
        },
    ),
)


def agent_benchmark_case_metadata() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "case_id": case.case_id,
            "query": case.query,
            "target_file": case.target_file,
            "expected_stop_reason": case.expected_stop_reason,
            "metadata": case.metadata or {},
        }
        for case in INTERNAL_AGENT_BENCHMARK_CASES
    )


def run_homllm_agent_benchmark(
    *,
    config_path: Path,
    source_workspace_root: Path,
    workspace_root: Path,
    artifact_root: Path,
    run_id: str | None = None,
    case_ids: tuple[str, ...] | None = None,
    cases: tuple[AgentBenchmarkCase, ...] | None = None,
    answer_provider_mode: str = "summary",
    live_provider_name: str = "gemini",
    live_model: str = "gemini-3.1-flash-lite-preview",
    live_api_key: str | None = None,
    live_max_output_tokens: int = 8192,
    max_prompt_chars: int | None = 22000,
    provider_repair_attempts: int = 1,
    smoke_safe: bool = True,
    index_skip_vectors: bool = False,
    edit_provider_mode: str = "live",
    agent_runner=run_homllm_agent,
) -> EvaluationRunResult:
    config_path = Path(config_path)
    if not config_path.exists():
        raise ValueError(f"config_not_found: {config_path}")

    source_workspace_root = Path(source_workspace_root).resolve()
    if not source_workspace_root.exists():
        raise ValueError(f"source_workspace_root_not_found: {source_workspace_root}")

    if edit_provider_mode not in {"fake", "live"}:
        raise ValueError(f"unsupported_edit_provider_mode: {edit_provider_mode}")
    if (answer_provider_mode == "live" or edit_provider_mode == "live") and not live_api_key:
        raise ValueError("live_api_key_required")

    resolved_run_id = run_id or str(uuid4())
    workspace_root = Path(workspace_root).resolve()
    artifact_root = Path(artifact_root).resolve()
    cases = cases if cases is not None else _select_cases(case_ids)

    for case in cases:
        target = workspace_root / resolved_run_id / "cases" / case.case_id
        if target.exists():
            raise ValueError(f"case_workspace_exists: {target}")
    artifact_manager = ArtifactManager(
        workspace_root=workspace_root,
        artifact_root=artifact_root,
    )
    artifact_manager.create_run(
        resolved_run_id,
        {
            "entrypoint": "homllm_v4.evaluation.agent_benchmark.run_homllm_agent_benchmark",
            "case_count": len(cases),
        },
    )
    case_results = tuple(
        _run_case(
            case=case,
            benchmark_run_id=resolved_run_id,
            config_path=Path(config_path),
            source_workspace_root=case.source_workspace_root or source_workspace_root,
            workspace_root=workspace_root,
            artifact_root=artifact_root,
            answer_provider_mode=answer_provider_mode,
            live_provider_name=live_provider_name,
            live_model=live_model,
            live_api_key=live_api_key,
            live_max_output_tokens=live_max_output_tokens,
            max_prompt_chars=max_prompt_chars,
            provider_repair_attempts=provider_repair_attempts,
            smoke_safe=smoke_safe,
            index_skip_vectors=index_skip_vectors,
            edit_provider_mode=edit_provider_mode,
            agent_runner=agent_runner,
        )
        for case in cases
    )
    passed_cases = sum(1 for case_result in case_results if case_result.passed)
    result = EvaluationRunResult(
        run_id=resolved_run_id,
        total_cases=len(case_results),
        passed_cases=passed_cases,
        failed_cases=len(case_results) - passed_cases,
        case_results=case_results,
        summary_metrics=_summary_metrics(case_results),
    )
    artifact_manager.write_json(
        "evaluation/summary.json",
        result,
        "evaluation",
        "homllm-agent benchmark summary",
    )
    return result


def _run_case(
    *,
    case: AgentBenchmarkCase,
    benchmark_run_id: str,
    config_path: Path,
    source_workspace_root: Path,
    workspace_root: Path,
    artifact_root: Path,
    answer_provider_mode: str,
    live_provider_name: str,
    live_model: str,
    live_api_key: str | None,
    live_max_output_tokens: int,
    max_prompt_chars: int | None,
    provider_repair_attempts: int,
    smoke_safe: bool,
    index_skip_vectors: bool,
    edit_provider_mode: str,
    agent_runner,
) -> EvaluationCaseResult:
    case_workspace = _copy_case_workspace(
        source_workspace_root=source_workspace_root,
        workspace_root=workspace_root,
        benchmark_run_id=benchmark_run_id,
        case_id=case.case_id,
    )
    case_run_id = f"{benchmark_run_id}-{case.case_id}"
    edit_provider_builder = None
    edit_require_live_api_key = True
    if edit_provider_mode == "fake":
        provider_mode = _case_provider_mode(case)
        edit_provider_builder = _canned_provider_builder(provider_mode)
        edit_require_live_api_key = False
    try:
        result: HomllmAgentRunResult = agent_runner(
            HomllmAgentRunRequest(
                config_path=config_path,
                workspace_root=case_workspace,
                artifact_root=artifact_root,
                run_id=case_run_id,
                query=case.query,
                smoke_safe=smoke_safe,
                answer_provider_mode=answer_provider_mode,
                edit_intent=case.edit_intent,
                expected_behavior=case.expected_behavior,
                target_file=case.target_file,
                verification_argv=case.verification_argv,
                live_provider_name=live_provider_name,
                live_model=live_model,
                live_api_key=live_api_key,
                live_max_output_tokens=live_max_output_tokens,
                max_prompt_chars=max_prompt_chars,
                provider_repair_attempts=provider_repair_attempts,
                prepare_index=case.prepare_index,
                index_skip_vectors=index_skip_vectors,
                edit_provider_builder=edit_provider_builder,
                edit_require_live_api_key=edit_require_live_api_key,
            )
        )
        metrics = _case_metrics(case, result)
        quality_failures = _quality_gate_failures(case, result, metrics)
        metrics["benchmark_quality_failures"] = quality_failures
        metrics["benchmark_quality_gate"] = "failed" if quality_failures else "passed"
        metrics["benchmark_quality_failure_count"] = len(quality_failures)
        passed = not quality_failures
        error_code = result.error_code
        if not passed and error_code is None:
            error_code = "benchmark_quality_gate_failed"
        return EvaluationCaseResult(
            case_id=case.case_id,
            runner_id="homllm-agent",
            task_type="mvp_coding_agent",
            expected_stop_reason=case.expected_stop_reason,
            actual_stop_reason=result.stop_reason,
            passed=passed,
            metrics=metrics,
            error_code=error_code,
        )
    except Exception as exc:
        return EvaluationCaseResult(
            case_id=case.case_id,
            runner_id="homllm-agent",
            task_type="mvp_coding_agent",
            expected_stop_reason=case.expected_stop_reason,
            actual_stop_reason=None,
            passed=False,
            metrics={
                "runner_exception_type": type(exc).__name__,
                "runner_exception_message": str(exc),
            },
            error_code=f"runner_exception:{type(exc).__name__}",
        )


def _quality_gate_failures(
    case: AgentBenchmarkCase,
    result: HomllmAgentRunResult,
    metrics: dict[str, object],
) -> tuple[str, ...]:
    failures: list[str] = []
    if result.stop_reason != case.expected_stop_reason:
        failures.append("stop_reason_mismatch")
    if result.error_code != case.expected_error_code:
        failures.append("error_code_mismatch")

    # Negative cases intentionally expect a failure and do not require the
    # successful-run trajectory stages below.
    if case.expected_stop_reason != "verified" or case.expected_error_code is not None:
        return tuple(failures)

    if case.prepare_index and (
        result.index_built is not True
        or metrics.get("trajectory_repo_index_status") != "built"
    ):
        failures.append("repo_index_not_built")
    if metrics.get("trajectory_grounded_answer_status") != "sufficient":
        failures.append("grounded_answer_not_sufficient")
    if metrics.get("trajectory_bounded_edit_status") != "verified":
        failures.append("bounded_edit_not_verified")
    if metrics.get("trajectory_verification_status") != "passed":
        failures.append("verification_not_passed")
    if not Path(result.session_state_path).is_file():
        failures.append("session_artifact_missing")
    if not Path(result.trajectory_path).is_file():
        failures.append("trajectory_artifact_missing")
    return tuple(failures)


def _case_provider_mode(case: AgentBenchmarkCase) -> str:
    metadata = case.metadata or {}
    return str(metadata.get("provider_mode", "noop"))


def _canned_provider_builder(provider_mode: str):
    provider = PromptAwareCannedProvider(provider_mode=provider_mode)

    def builder(**kwargs):
        return provider

    return builder


def _case_metrics(
    case: AgentBenchmarkCase,
    result: HomllmAgentRunResult,
) -> dict[str, object]:
    trajectory = _read_trajectory(Path(result.trajectory_path))
    steps = trajectory.get("steps", [])
    step_statuses = {
        str(step.get("name")): str(step.get("status"))
        for step in steps
        if isinstance(step, dict)
    } if isinstance(steps, list) else {}
    metrics_payload = trajectory.get("metrics", {})
    metrics: dict[str, object] = {
        "patch_attempt_count": result.patch_attempt_count,
        "provider_repair_attempt_count": result.provider_repair_attempt_count,
        "verification_count": result.verification_count,
        "index_built": result.index_built,
        "answer_provider_mode": result.answer_provider_mode,
        "trajectory_step_count": len(steps) if isinstance(steps, list) else 0,
        "trajectory_repo_index_status": step_statuses.get("repo_index"),
        "trajectory_grounded_answer_status": step_statuses.get("grounded_answer"),
        "trajectory_bounded_edit_status": step_statuses.get("bounded_edit"),
        "trajectory_verification_status": step_statuses.get("verification"),
    }
    metrics.update(case.metadata or {})
    if isinstance(metrics_payload, dict):
        metrics["provider_tokens_in"] = _nested_numeric_total(
            metrics_payload,
            "provider_tokens_in",
        )
        metrics["provider_tokens_out"] = _nested_numeric_total(
            metrics_payload,
            "provider_tokens_out",
        )
        index_metrics = metrics_payload.get("index")
        if isinstance(index_metrics, dict) and isinstance(
            index_metrics.get("source_file_count"),
            (int, float),
        ):
            metrics["index_source_file_count"] = float(
                index_metrics["source_file_count"]
            )
    if "index_source_file_count" not in metrics and result.index_metrics:
        source_count = result.index_metrics.get("source_file_count")
        if isinstance(source_count, (int, float)):
            metrics["index_source_file_count"] = float(source_count)
    return metrics


def _summary_metrics(results: tuple[EvaluationCaseResult, ...]) -> dict[str, object]:
    stop_reason_counts: dict[str, int] = {}
    error_code_counts: dict[str, int] = {}
    numeric_totals: dict[str, float] = {}
    numeric_counts: dict[str, int] = {}
    categorical_counts: dict[str, dict[str, int]] = {}
    for result in results:
        if result.actual_stop_reason is not None:
            stop_reason_counts[result.actual_stop_reason] = (
                stop_reason_counts.get(result.actual_stop_reason, 0) + 1
            )
        if result.error_code is not None:
            error_code_counts[result.error_code] = (
                error_code_counts.get(result.error_code, 0) + 1
            )
        for key, value in result.metrics.items():
            if isinstance(value, bool):
                bucket = categorical_counts.setdefault(key, {})
                bucket[str(value)] = bucket.get(str(value), 0) + 1
            elif isinstance(value, (int, float)):
                numeric_totals[key] = numeric_totals.get(key, 0.0) + float(value)
                numeric_counts[key] = numeric_counts.get(key, 0) + 1
            elif isinstance(value, str):
                bucket = categorical_counts.setdefault(key, {})
                bucket[value] = bucket.get(value, 0) + 1
    return {
        "stop_reason_counts": dict(sorted(stop_reason_counts.items())),
        "error_code_counts": dict(sorted(error_code_counts.items())),
        "numeric_metric_totals": dict(sorted(numeric_totals.items())),
        "numeric_metric_averages": {
            key: numeric_totals[key] / numeric_counts[key]
            for key in sorted(numeric_totals)
        },
        "categorical_metric_counts": {
            key: dict(sorted(value.items()))
            for key, value in sorted(categorical_counts.items())
        },
        "baseline_case_count": 0,
    }


def _select_cases(case_ids: tuple[str, ...] | None) -> tuple[AgentBenchmarkCase, ...]:
    if case_ids is None:
        return INTERNAL_AGENT_BENCHMARK_CASES
    by_id = {case.case_id: case for case in INTERNAL_AGENT_BENCHMARK_CASES}
    missing = tuple(case_id for case_id in case_ids if case_id not in by_id)
    if missing:
        raise ValueError(f"unknown_agent_benchmark_case: {missing[0]}")
    return tuple(by_id[case_id] for case_id in case_ids)


def _copy_case_workspace(
    *,
    source_workspace_root: Path,
    workspace_root: Path,
    benchmark_run_id: str,
    case_id: str,
) -> Path:
    target = workspace_root / benchmark_run_id / "cases" / case_id
    if target.exists():
        raise ValueError(f"case_workspace_exists: {target}")
    shutil.copytree(
        source_workspace_root,
        target,
        ignore=_ignore_workspace_copy_artifacts,
    )
    return target


def _ignore_workspace_copy_artifacts(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name == "__pycache__" or name.endswith((".pyc", ".pyo"))
    }


def _read_trajectory(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("trajectory_invalid: expected object")
    return data


def _nested_numeric_total(payload: dict[str, object], key: str) -> float:
    total = 0.0
    for value in payload.values():
        if isinstance(value, dict) and isinstance(value.get(key), (int, float)):
            total += float(value[key])
    return total
