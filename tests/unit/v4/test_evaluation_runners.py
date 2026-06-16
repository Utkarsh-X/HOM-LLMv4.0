from homllm_v4.contracts.evaluation import EvaluationCase
from homllm_v4.contracts.loop import ReadOnlyLoopRequest, ReadOnlyLoopResult, SufficiencyDecision
from homllm_v4.contracts.command import CommandRunResult
from homllm_v4.contracts.write_loop import WriteVerifyLoopRequest, WriteVerifyLoopResult
from homllm_v4.evaluation.runners import make_read_only_runner, make_write_verify_runner


class FakeReadOnlyLoop:
    def __init__(self, result: ReadOnlyLoopResult) -> None:
        self.result = result
        self.requests: list[ReadOnlyLoopRequest] = []

    def run(self, request: ReadOnlyLoopRequest) -> ReadOnlyLoopResult:
        self.requests.append(request)
        return self.result


class FakeWriteVerifyLoop:
    def __init__(self, result: WriteVerifyLoopResult) -> None:
        self.result = result
        self.requests: list[WriteVerifyLoopRequest] = []

    def run(self, request: WriteVerifyLoopRequest) -> WriteVerifyLoopResult:
        self.requests.append(request)
        return self.result


def test_read_only_evaluation_runner_maps_loop_result_metrics() -> None:
    request = ReadOnlyLoopRequest(
        task_id="task-1",
        run_id="run-1",
        workspace_root=".",
        query="explain demo",
    )
    loop = FakeReadOnlyLoop(
        ReadOnlyLoopResult(
            task_id="task-1",
            run_id="run-1",
            stop_reason="sufficient",
            pass_count=2,
            sufficiency=SufficiencyDecision(True, 1.0, (), 3, 3),
            passes=(),
            context_pack=None,
            response_text="ok",
            claim_support=(),
            error=None,
        )
    )
    runner = make_read_only_runner(loop, lambda case: request)

    result = runner(
        EvaluationCase(
            case_id="case-1",
            runner_id="read_only",
            task_type="read_only",
            input_payload={},
            expected_stop_reason="sufficient",
        )
    )

    assert loop.requests == [request]
    assert result.stop_reason == "sufficient"
    assert result.metrics == {
        "pass_count": 2,
        "sufficiency_score": 1.0,
        "claim_support_count": 0,
    }
    assert result.error_code is None


def test_write_verify_evaluation_runner_maps_loop_result_metrics() -> None:
    request = WriteVerifyLoopRequest(
        task_id="task-1",
        run_id="run-1",
        workspace_root=".",
        patch_request=None,
        verification_commands=(),
    )
    loop = FakeWriteVerifyLoop(
        WriteVerifyLoopResult(
            task_id="task-1",
            run_id="run-1",
            stop_reason="verified",
            patch_result=None,
            verification_results=(
                CommandRunResult(
                    argv=("pytest", "-q"),
                    cwd=".",
                    exit_code=0,
                    stdout="one two three",
                    stderr="",
                    duration_ms=12,
                    timed_out=False,
                    denied=False,
                ),
            ),
            response_text="verified",
            patch_attempt_count=2,
            error=None,
        )
    )
    runner = make_write_verify_runner(loop, lambda case: request)

    result = runner(
        EvaluationCase(
            case_id="case-1",
            runner_id="write_verify",
            task_type="write_verify",
            input_payload={},
            expected_stop_reason="verified",
        )
    )

    assert loop.requests == [request]
    assert result.stop_reason == "verified"
    assert result.metrics == {
        "patch_attempt_count": 2,
        "verification_count": 1,
        "verification_duration_ms": 12,
        "verification_output_chars": 13,
        "verification_output_token_estimate": 3,
    }
    assert result.error_code is None
