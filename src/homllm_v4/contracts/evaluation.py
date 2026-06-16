from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    runner_id: str
    task_type: str
    input_payload: dict[str, object]
    expected_stop_reason: str
    expected_error_code: str | None = None
    baseline_runner_id: str | None = None


@dataclass(frozen=True)
class CaseExecutionResult:
    stop_reason: str
    metrics: dict[str, object]
    error_code: str | None = None


@dataclass(frozen=True)
class EvaluationCaseResult:
    case_id: str
    runner_id: str
    task_type: str
    expected_stop_reason: str
    actual_stop_reason: str | None
    passed: bool
    metrics: dict[str, object]
    error_code: str | None
    baseline_runner_id: str | None = None
    baseline_stop_reason: str | None = None
    baseline_error_code: str | None = None
    baseline_metrics: dict[str, object] | None = None
    metric_deltas: dict[str, float] | None = None


@dataclass(frozen=True)
class EvaluationRunResult:
    run_id: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    case_results: tuple[EvaluationCaseResult, ...]
    summary_metrics: dict[str, object]
