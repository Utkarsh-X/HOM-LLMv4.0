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
        argv=(
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


def failed_plan(code: str) -> CapabilityResult[EvidenceBackedPatchPlanResult]:
    return CapabilityResult(
        capability_name="patch.plan.provider_proposed",
        ok=False,
        output=None,
        error=CapabilityError(
            code=code,
            message="planner failed",
            recoverable=True,
            retryable=True,
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
    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == "VALUE = 3\n"


def test_provider_write_verify_runner_surfaces_planner_failure(tmp_path: Path) -> None:
    planner = SequencePlanner((failed_plan("provider_invocation_failed"),))

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
    assert result.error_code == "provider_invocation_failed"
    assert result.patch_attempt_count == 0
    assert result.verification_results == ()
