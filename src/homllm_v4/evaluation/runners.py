from collections.abc import Callable

from homllm_v4.contracts.evaluation import CaseExecutionResult, EvaluationCase
from homllm_v4.contracts.loop import ReadOnlyLoopRequest, ReadOnlyLoopResult
from homllm_v4.contracts.write_loop import WriteVerifyLoopRequest, WriteVerifyLoopResult

ReadOnlyRequestFactory = Callable[[EvaluationCase], ReadOnlyLoopRequest]
WriteVerifyRequestFactory = Callable[[EvaluationCase], WriteVerifyLoopRequest]


def make_read_only_runner(
    loop: object,
    request_factory: ReadOnlyRequestFactory,
) -> Callable[[EvaluationCase], CaseExecutionResult]:
    def run(case: EvaluationCase) -> CaseExecutionResult:
        result: ReadOnlyLoopResult = loop.run(request_factory(case))
        return CaseExecutionResult(
            stop_reason=result.stop_reason,
            metrics={
                "pass_count": result.pass_count,
                "sufficiency_score": result.sufficiency.score,
                "claim_support_count": len(result.claim_support),
            },
            error_code=result.error.code if result.error else None,
        )

    return run


def make_write_verify_runner(
    loop: object,
    request_factory: WriteVerifyRequestFactory,
) -> Callable[[EvaluationCase], CaseExecutionResult]:
    def run(case: EvaluationCase) -> CaseExecutionResult:
        result: WriteVerifyLoopResult = loop.run(request_factory(case))
        output_chars = sum(
            len(command.stdout or "") + len(command.stderr or "")
            for command in result.verification_results
        )
        return CaseExecutionResult(
            stop_reason=result.stop_reason,
            metrics={
                "patch_attempt_count": result.patch_attempt_count,
                "verification_count": len(result.verification_results),
                "verification_duration_ms": sum(
                    int(command.duration_ms) for command in result.verification_results
                ),
                "verification_output_chars": output_chars,
                "verification_output_token_estimate": output_chars // 4,
            },
            error_code=result.error.code if result.error else None,
        )

    return run
