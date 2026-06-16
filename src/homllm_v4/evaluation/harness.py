from collections.abc import Callable

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.evaluation import (
    CaseExecutionResult,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationRunResult,
)

CaseRunner = Callable[[EvaluationCase], CaseExecutionResult]


class V4EvaluationHarness:
    def __init__(
        self,
        *,
        artifact_manager: ArtifactManager,
        runners: dict[str, CaseRunner],
    ) -> None:
        self.artifact_manager = artifact_manager
        self.runners = dict(runners)

    def run(
        self,
        *,
        run_id: str,
        cases: tuple[EvaluationCase, ...],
    ) -> EvaluationRunResult:
        results = tuple(self._run_case(case) for case in cases)
        passed = sum(1 for result in results if result.passed)
        output = EvaluationRunResult(
            run_id=run_id,
            total_cases=len(results),
            passed_cases=passed,
            failed_cases=len(results) - passed,
            case_results=results,
            summary_metrics=self._summary_metrics(results),
        )
        self.artifact_manager.write_json(
            "evaluation/summary.json",
            output,
            "evaluation",
            "v4 evaluation summary",
        )
        return output

    def _run_case(self, case: EvaluationCase) -> EvaluationCaseResult:
        runner = self.runners.get(case.runner_id)
        if runner is None:
            return EvaluationCaseResult(
                case_id=case.case_id,
                runner_id=case.runner_id,
                task_type=case.task_type,
                expected_stop_reason=case.expected_stop_reason,
                actual_stop_reason=None,
                passed=False,
                metrics={},
                error_code="unknown_runner",
            )

        try:
            execution = runner(case)
        except Exception as exc:
            return EvaluationCaseResult(
                case_id=case.case_id,
                runner_id=case.runner_id,
                task_type=case.task_type,
                expected_stop_reason=case.expected_stop_reason,
                actual_stop_reason=None,
                passed=False,
                metrics={
                    "runner_exception_type": type(exc).__name__,
                    "runner_exception_message": str(exc),
                },
                error_code=f"runner_exception:{type(exc).__name__}",
            )

        passed = (
            execution.stop_reason == case.expected_stop_reason
            and execution.error_code == case.expected_error_code
        )
        baseline = self._run_baseline(case)
        return EvaluationCaseResult(
            case_id=case.case_id,
            runner_id=case.runner_id,
            task_type=case.task_type,
            expected_stop_reason=case.expected_stop_reason,
            actual_stop_reason=execution.stop_reason,
            passed=passed,
            metrics=execution.metrics,
            error_code=execution.error_code,
            baseline_runner_id=case.baseline_runner_id,
            baseline_stop_reason=baseline.stop_reason if baseline else None,
            baseline_error_code=baseline.error_code if baseline else None,
            baseline_metrics=baseline.metrics if baseline else None,
            metric_deltas=self._metric_deltas(execution, baseline),
        )

    def _run_baseline(self, case: EvaluationCase) -> CaseExecutionResult | None:
        if case.baseline_runner_id is None:
            return None
        runner = self.runners.get(case.baseline_runner_id)
        if runner is None:
            return CaseExecutionResult(
                stop_reason="baseline_unavailable",
                metrics={},
                error_code="unknown_baseline_runner",
            )
        try:
            return runner(case)
        except Exception as exc:
            return CaseExecutionResult(
                stop_reason="baseline_exception",
                metrics={},
                error_code=f"baseline_exception:{type(exc).__name__}",
            )

    @staticmethod
    def _metric_deltas(
        execution: CaseExecutionResult,
        baseline: CaseExecutionResult | None,
    ) -> dict[str, float] | None:
        if baseline is None:
            return None
        deltas: dict[str, float] = {}
        for key, value in execution.metrics.items():
            baseline_value = baseline.metrics.get(key)
            if isinstance(value, (int, float)) and isinstance(baseline_value, (int, float)):
                deltas[key] = float(value) - float(baseline_value)
        return deltas

    @staticmethod
    def _summary_metrics(results: tuple[EvaluationCaseResult, ...]) -> dict[str, object]:
        stop_reason_counts: dict[str, int] = {}
        error_code_counts: dict[str, int] = {}
        numeric_totals: dict[str, float] = {}
        numeric_counts: dict[str, int] = {}
        categorical_counts: dict[str, dict[str, int]] = {}
        baseline_case_count = 0

        for result in results:
            if result.actual_stop_reason is not None:
                stop_reason_counts[result.actual_stop_reason] = (
                    stop_reason_counts.get(result.actual_stop_reason, 0) + 1
                )
            if result.error_code is not None:
                error_code_counts[result.error_code] = error_code_counts.get(result.error_code, 0) + 1
            if result.baseline_runner_id is not None:
                baseline_case_count += 1
            for key, value in result.metrics.items():
                if isinstance(value, (str, bool)):
                    value_key = str(value)
                    metric_counts = categorical_counts.setdefault(key, {})
                    metric_counts[value_key] = metric_counts.get(value_key, 0) + 1
                elif isinstance(value, (int, float)):
                    numeric_totals[key] = numeric_totals.get(key, 0.0) + float(value)
                    numeric_counts[key] = numeric_counts.get(key, 0) + 1

        numeric_averages = {
            key: numeric_totals[key] / numeric_counts[key]
            for key in sorted(numeric_totals)
        }
        return {
            "stop_reason_counts": dict(sorted(stop_reason_counts.items())),
            "error_code_counts": dict(sorted(error_code_counts.items())),
            "numeric_metric_totals": dict(sorted(numeric_totals.items())),
            "numeric_metric_averages": numeric_averages,
            "categorical_metric_counts": {
                key: dict(sorted(values.items()))
                for key, values in sorted(categorical_counts.items())
            },
            "baseline_case_count": baseline_case_count,
        }
