import hashlib
import sys
from pathlib import Path

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.command import CommandPolicy, CommandRunRequest
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.patch import FilePatch, PatchApplyRequest
from homllm_v4.contracts.patch_plan import EvidenceBackedPatchPlanResult, PatchPlan
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.planning.provider_patch_planner import ProviderProposedPatchPlanRequest
from homllm_v4.runtime.provider_write_verify_runner import (
    ProviderWriteVerifyRunRequest,
    ProviderWriteVerifyRunner,
    _previous_attempt_diff,
    _pytest_failure_summary,
    _repair_context,
    _tail_diagnostic,
)
from homllm_v4.runtime.write_verify_loop import WriteVerifyLoop
from homllm_v4.services.command_service import LocalCommandService
from homllm_v4.services.patch_service import WorkspacePatchService


def content_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def make_loop(tmp_path: Path) -> WriteVerifyLoop:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("run-1", {})
    return WriteVerifyLoop(
        patch_service=WorkspacePatchService(),
        command_service=LocalCommandService(
            policy=CommandPolicy(
                allowed_executables=(Path(sys.executable).name,),
                default_timeout_seconds=5,
                max_timeout_seconds=5,
            )
        ),
        artifact_manager=manager,
        event_writer=EventWriter(tmp_path / ".homllm" / "runs" / "run-1" / "events.jsonl"),
    )


def plan_request(tmp_path: Path) -> ProviderProposedPatchPlanRequest:
    return ProviderProposedPatchPlanRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        query="fix value",
        task_class="python_patch",
        index_id="idx",
        target_file="demo.py",
        intent="make VALUE equal 3",
        expected_behavior="verification passes when VALUE is 3",
        verification_argv=(
            sys.executable,
            "-c",
            "from pathlib import Path; "
            "raise SystemExit(0 if Path('demo.py').read_text() == 'VALUE = 3\\n' else 1)",
        ),
        retrieval_policy={"intent": "PATCH", "top_k": 5},
    )


def successful_plan(
    tmp_path: Path,
    *,
    new_content: str,
    expected_content: str,
    tokens_in: int,
    tokens_out: int,
    verification_argv: tuple[str, ...] | None = None,
) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
    patch_request = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash(expected_content), new_content),),
    )
    verification = CommandRunRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        cwd=".",
        argv=verification_argv
        or (
            sys.executable,
            "-c",
            "from pathlib import Path; "
            "raise SystemExit(0 if Path('demo.py').read_text() == 'VALUE = 3\\n' else 1)",
        ),
        timeout_seconds=5,
    )
    return CapabilityResult(
        capability_name="patch.plan.provider_proposed",
        ok=True,
        output=EvidenceBackedPatchPlanResult(
            patch_plan=PatchPlan(
                patch_plan_id="plan-1",
                task_id="task-1",
                intent="make VALUE equal 3",
                target_files=("demo.py",),
                evidence_ids=("cand-1",),
                expected_behavior="verification passes when VALUE is 3",
                verification_gates=("python -c",),
                risk_flags=(),
                user_visible_summary="patch demo.py",
            ),
            patch_request=patch_request,
            verification_commands=(verification,),
        ),
        error=None,
        telemetry=CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=0,
            input_summary={"task_id": "task-1"},
            output_summary={
                "prompt_char_count": 100,
                "evidence_context_item_count": 1,
                "evidence_context_rendered_char_count": 20,
                "evidence_context_truncated": False,
                "target_selection_decision": "supplied",
                "resolved_target_file": "demo.py",
            },
            token_usage={"input": tokens_in, "output": tokens_out},
            model_usage={"model": "fake"},
            degraded=False,
            degradation_reason=None,
        ),
        artifacts=(),
    )


def failed_plan(
    code: str,
    *,
    retryable: bool = True,
) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
    return CapabilityResult(
        capability_name="patch.plan.provider_proposed",
        ok=False,
        output=None,
        error=CapabilityError(
            code=code,
            message="planner failed",
            recoverable=True,
            retryable=retryable,
        ),
        telemetry=CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=0,
            input_summary={"task_id": "task-1"},
            output_summary={"code": code},
            token_usage={},
            model_usage={},
            degraded=False,
            degradation_reason=None,
        ),
        artifacts=(),
    )


class SequencePlanner:
    def __init__(self, plans) -> None:
        self.plans = list(plans)
        self.repair_contexts: list[str] = []

    def plan(self, request: ProviderProposedPatchPlanRequest):
        if request.repair_context:
            self.repair_contexts.append(request.repair_context)
        return self.plans.pop(0)


def test_provider_write_verify_runner_repairs_after_verification_failure(
    tmp_path: Path,
) -> None:
    (tmp_path / "demo.py").write_text("VALUE = 1\n", encoding="utf-8")
    planner = SequencePlanner(
        (
            successful_plan(
                tmp_path,
                new_content="VALUE = 2\n",
                expected_content="VALUE = 1\n",
                tokens_in=101,
                tokens_out=11,
            ),
            successful_plan(
                tmp_path,
                new_content="VALUE = 3\n",
                expected_content="VALUE = 1\n",
                tokens_in=102,
                tokens_out=12,
            ),
        )
    )

    result = ProviderWriteVerifyRunner(
        planner=planner,
        write_verify_loop=make_loop(tmp_path),
    ).run(
        ProviderWriteVerifyRunRequest(
            task_id="task-1",
            run_id="run-1",
            workspace_root=str(tmp_path),
            plan_request=plan_request(tmp_path),
            provider_repair_attempts=1,
        )
    )

    assert result.stop_reason == "verified"
    assert result.patch_attempt_count == 2
    assert result.provider_repair_attempt_count == 1
    assert result.planner_metrics["provider_tokens_in"] == 203
    assert result.planner_metrics["provider_tokens_out"] == 23
    assert "Previous verification stopped with reason verification_failed" in (
        planner.repair_contexts[0]
    )
    # The repair prompt must show the model the exact change its failed
    # attempt applied (VALUE = 1 -> 2), not just the failure verdict, so the
    # next plan can correct the specific mistake.
    assert "VALUE = 1" in planner.repair_contexts[0]
    assert "VALUE = 2" in planner.repair_contexts[0]
    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == "VALUE = 3\n"


def test_previous_attempt_diff_requires_original_content_on_disk(
    tmp_path: Path,
) -> None:
    (tmp_path / "demo.py").write_text("VALUE = 1\n", encoding="utf-8")
    previous = successful_plan(
        tmp_path,
        new_content="VALUE = 2\n",
        expected_content="VALUE = 1\n",
        tokens_in=1,
        tokens_out=1,
    )

    diff = _previous_attempt_diff(previous)

    assert diff is not None
    assert "a/demo.py" in diff
    assert "-VALUE = 1" in diff
    assert "+VALUE = 2" in diff

    # If the workspace no longer holds the original (no rollback happened),
    # the hash guard must suppress the diff rather than emit a misleading one.
    (tmp_path / "demo.py").write_text("VALUE = 99\n", encoding="utf-8")
    assert _previous_attempt_diff(previous) is None


def test_provider_write_verify_runner_surfaces_non_retryable_planner_failure(
    tmp_path: Path,
) -> None:
    planner = SequencePlanner((failed_plan("target_selection_failed", retryable=False),))

    result = ProviderWriteVerifyRunner(
        planner=planner,
        write_verify_loop=make_loop(tmp_path),
    ).run(
        ProviderWriteVerifyRunRequest(
            task_id="task-1",
            run_id="run-1",
            workspace_root=str(tmp_path),
            plan_request=plan_request(tmp_path),
            provider_repair_attempts=1,
        )
    )

    assert result.stop_reason == "patch_failed"
    assert result.error_code == "target_selection_failed"
    assert result.patch_attempt_count == 0
    assert result.provider_repair_attempt_count == 0
    assert result.verification_results == ()
    assert len(result.plan_results) == 1


def test_provider_write_verify_runner_replans_after_retryable_plan_failure(
    tmp_path: Path,
) -> None:
    (tmp_path / "demo.py").write_text("VALUE = 1\n", encoding="utf-8")
    planner = SequencePlanner(
        (
            failed_plan("provider_response_invalid"),
            successful_plan(
                tmp_path,
                new_content="VALUE = 3\n",
                expected_content="VALUE = 1\n",
                tokens_in=101,
                tokens_out=11,
            ),
        )
    )

    result = ProviderWriteVerifyRunner(
        planner=planner,
        write_verify_loop=make_loop(tmp_path),
    ).run(
        ProviderWriteVerifyRunRequest(
            task_id="task-1",
            run_id="run-1",
            workspace_root=str(tmp_path),
            plan_request=plan_request(tmp_path),
            provider_repair_attempts=1,
        )
    )

    assert result.stop_reason == "verified"
    assert result.patch_attempt_count == 1
    assert result.provider_repair_attempt_count == 1
    assert len(result.plan_results) == 2
    assert "provider_response_invalid" in planner.repair_contexts[0]
    assert "Return valid JSON" in planner.repair_contexts[0]


def test_provider_write_verify_runner_plan_retry_budget_exhausted(
    tmp_path: Path,
) -> None:
    planner = SequencePlanner(
        (
            failed_plan("provider_response_invalid"),
            failed_plan("provider_response_truncated"),
        )
    )

    result = ProviderWriteVerifyRunner(
        planner=planner,
        write_verify_loop=make_loop(tmp_path),
    ).run(
        ProviderWriteVerifyRunRequest(
            task_id="task-1",
            run_id="run-1",
            workspace_root=str(tmp_path),
            plan_request=plan_request(tmp_path),
            provider_repair_attempts=1,
        )
    )

    assert result.stop_reason == "patch_failed"
    assert result.error_code == "provider_response_truncated"
    assert result.provider_repair_attempt_count == 1
    assert len(result.plan_results) == 2
    assert result.verification_results == ()


def test_provider_write_verify_runner_replans_after_empty_evidence_proposal(
    tmp_path: Path,
) -> None:
    # A provider that drops evidence_ids (e.g. a repair attempt that
    # over-corrects) must be replanned with a repair prompt instead of
    # hard-stopping the case.
    (tmp_path / "demo.py").write_text("VALUE = 1\n", encoding="utf-8")
    planner = SequencePlanner(
        (
            failed_plan("proposal_missing_evidence"),
            successful_plan(
                tmp_path,
                new_content="VALUE = 3\n",
                expected_content="VALUE = 1\n",
                tokens_in=101,
                tokens_out=11,
            ),
        )
    )

    result = ProviderWriteVerifyRunner(
        planner=planner,
        write_verify_loop=make_loop(tmp_path),
    ).run(
        ProviderWriteVerifyRunRequest(
            task_id="task-1",
            run_id="run-1",
            workspace_root=str(tmp_path),
            plan_request=plan_request(tmp_path),
            provider_repair_attempts=1,
        )
    )

    assert result.stop_reason == "verified"
    assert result.provider_repair_attempt_count == 1
    assert "proposal_missing_evidence" in planner.repair_contexts[0]


def test_provider_write_verify_runner_replans_after_truncated_plan_response(
    tmp_path: Path,
) -> None:
    planner = SequencePlanner(
        (
            failed_plan("provider_response_truncated"),
            successful_plan(
                tmp_path,
                new_content="VALUE = 3\n",
                expected_content="VALUE = 1\n",
                tokens_in=101,
                tokens_out=11,
            ),
        )
    )
    (tmp_path / "demo.py").write_text("VALUE = 1\n", encoding="utf-8")

    result = ProviderWriteVerifyRunner(
        planner=planner,
        write_verify_loop=make_loop(tmp_path),
    ).run(
        ProviderWriteVerifyRunRequest(
            task_id="task-1",
            run_id="run-1",
            workspace_root=str(tmp_path),
            plan_request=plan_request(tmp_path),
            provider_repair_attempts=1,
        )
    )

    assert result.stop_reason == "verified"
    assert result.provider_repair_attempt_count == 1
    assert result.patch_attempt_count == 1
    assert "provider_response_truncated" in planner.repair_contexts[0]


def test_pytest_failure_summary_extracts_failed_node_ids() -> None:
    # pytest -q puts the actionable FAILED lines in the short test summary at
    # the END of the output; the start is traceback head noise. The summary
    # extraction must surface node ids and reasons, not the head window.
    class FakeResult:
        stdout = (
            "============================= test session starts =============================\n"
            "collecting ... collected 3 items\n\n"
            "test_arit.py::test_Abs F\n"
            "test_arit.py::test_sign .\n"
            "test_arit.py::test_issue F\n\n"
            "=============================== FAILURES =======================================\n"
            "_______________________________ test_Abs _____________________________________\n"
            "    def test_Abs():\n"
            ">       assert abs(-3) == 4\n"
            "E       assert 3 == 4\n"
            "=========================== short test summary info ============================\n"
            "FAILED sympy/core/tests/test_arit.py::test_Abs - assert 3 == 4\n"
            "FAILED sympy/core/tests/test_arit.py::test_issue_21627 - TypeError: bad\n"
            "======================== 2 failed, 1 passed in 3.50s ===========================\n"
        )
        stderr = ""

    summary = _pytest_failure_summary(FakeResult())

    assert summary is not None
    assert "Failing tests:" in summary
    assert "sympy/core/tests/test_arit.py::test_Abs - assert 3 == 4" in summary
    assert "sympy/core/tests/test_arit.py::test_issue_21627 - TypeError: bad" in summary
    assert "Summary: 2 failed, 1 passed" in summary


def test_pytest_failure_summary_returns_none_for_non_pytest_output() -> None:
    class FakeResult:
        stdout = "VALUE = 1\n"
        stderr = ""

    assert _pytest_failure_summary(FakeResult()) is None


def test_repair_context_uses_failure_summary_when_available() -> None:
    class FakeCommand:
        exit_code = 1
        timed_out = False
        stdout = (
            "=========================== short test summary info ============================\n"
            "FAILED sympy/core/tests/test_arit.py::test_Abs - assert 3 == 4\n"
            "======================== 1 failed, 1 passed in 3.50s ===========================\n"
        )
        stderr = ""

    class FakeResult:
        stop_reason = "verification_failed"
        verification_results = (FakeCommand(),)

    context = _repair_context(FakeResult())

    assert "Previous verification stopped with reason verification_failed" in context
    assert "Failing tests:" in context
    assert "test_Abs" in context
    assert "stdout=" not in context


def test_repair_context_falls_back_to_tail_window() -> None:
    class FakeCommand:
        exit_code = 1
        timed_out = False
        stdout = "x" * 1200 + "\nfailure details live at the end"
        stderr = ""

    class FakeResult:
        stop_reason = "verification_failed"
        verification_results = (FakeCommand(),)

    context = _repair_context(FakeResult())

    assert "failure details live at the end" in context
    assert "...[truncated]" in context


def test_tail_diagnostic_keeps_the_end_not_the_start() -> None:
    body = "a" * 600
    assert _tail_diagnostic(body + "tail-info") == "...[truncated] " + "a" * 491 + "tail-info"
    assert _tail_diagnostic("short output") == "short output"


def test_provider_write_verify_runner_plan_retry_then_verification_repair(
    tmp_path: Path,
) -> None:
    (tmp_path / "demo.py").write_text("VALUE = 1\n", encoding="utf-8")
    planner = SequencePlanner(
        (
            failed_plan("provider_response_invalid"),
            successful_plan(
                tmp_path,
                new_content="VALUE = 2\n",
                expected_content="VALUE = 1\n",
                tokens_in=101,
                tokens_out=11,
            ),
            successful_plan(
                tmp_path,
                new_content="VALUE = 3\n",
                expected_content="VALUE = 1\n",
                tokens_in=102,
                tokens_out=12,
            ),
        )
    )

    result = ProviderWriteVerifyRunner(
        planner=planner,
        write_verify_loop=make_loop(tmp_path),
    ).run(
        ProviderWriteVerifyRunRequest(
            task_id="task-1",
            run_id="run-1",
            workspace_root=str(tmp_path),
            plan_request=plan_request(tmp_path),
            provider_repair_attempts=2,
        )
    )

    # Attempt 1: plan fails (invalid JSON) -> replan. Attempt 2: plan ok but
    # verification fails (VALUE=2) -> repair. Attempt 3: plan ok, verified.
    assert result.stop_reason == "verified"
    assert result.provider_repair_attempt_count == 2
    assert result.patch_attempt_count == 2
    assert len(planner.repair_contexts) == 2
    assert "provider_response_invalid" in planner.repair_contexts[0]
    assert "verification_failed" in planner.repair_contexts[1]


def test_provider_write_verify_runner_converges_from_pytest_failure_summary(
    tmp_path: Path,
) -> None:
    # Prove the repair loop can converge from a *pytest failure summary*
    # (the live SWE-bench milestone found the model repeating wrong edits
    # despite the summary being present). The first attempt fails a real
    # pytest run; the repair plan must receive the extracted "Failing tests:"
    # block and the second attempt must verify.
    (tmp_path / "demo.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "test_demo.py").write_text(
        "from pathlib import Path\n"
        "def test_value():\n"
        "    assert Path('demo.py').read_text(encoding='utf-8') == 'VALUE = 3\\n'\n",
        encoding="utf-8",
    )
    pytest_argv = (sys.executable, "-m", "pytest", "test_demo.py", "-q")
    planner = SequencePlanner(
        (
            successful_plan(
                tmp_path,
                new_content="VALUE = 2\n",
                expected_content="VALUE = 1\n",
                tokens_in=101,
                tokens_out=11,
                verification_argv=pytest_argv,
            ),
            successful_plan(
                tmp_path,
                new_content="VALUE = 3\n",
                expected_content="VALUE = 1\n",
                tokens_in=102,
                tokens_out=12,
                verification_argv=pytest_argv,
            ),
        )
    )

    result = ProviderWriteVerifyRunner(
        planner=planner,
        write_verify_loop=make_loop(tmp_path),
    ).run(
        ProviderWriteVerifyRunRequest(
            task_id="task-1",
            run_id="run-1",
            workspace_root=str(tmp_path),
            plan_request=plan_request(tmp_path),
            provider_repair_attempts=1,
        )
    )

    assert result.stop_reason == "verified"
    assert result.patch_attempt_count == 2
    assert result.provider_repair_attempt_count == 1
    assert len(planner.repair_contexts) == 1
    repair_context = planner.repair_contexts[0]
    assert "Failing tests:" in repair_context
    assert "test_demo.py::test_value" in repair_context
    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == "VALUE = 3\n"
