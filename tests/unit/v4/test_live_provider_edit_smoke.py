import hashlib
import os
import shutil
import sys
from pathlib import Path

import pytest

from homllm.generation.interfaces import ModelConfig
from homllm_v4.adapters.v3_provider_factory import build_v3_provider_edit_adapter
from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.command import CommandPolicy, CommandRunRequest
from homllm_v4.contracts.edit_proposal import EditProposalRequest
from homllm_v4.contracts.evidence import (
    EvidenceCandidate,
    EvidenceRetrievalRequest,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.contracts.write_loop import WriteVerifyLoopRequest
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.planning.provider_edit_proposer import ProviderBackedEditProposer
from homllm_v4.planning.provider_patch_planner import (
    ProviderProposedPatchPlanRequest,
    ProviderProposedPatchPlanner,
)
from homllm_v4.runtime.write_verify_loop import WriteVerifyLoop
from homllm_v4.services.command_service import LocalCommandService
from homllm_v4.services.direct_read_service import DirectReadService
from homllm_v4.services.patch_service import WorkspacePatchService


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


class _FixtureRetrievalService:
    def __init__(self, evidence: EvidenceSet) -> None:
        self.evidence = evidence

    def retrieve(self, request: EvidenceRetrievalRequest) -> CapabilityResult[EvidenceSet]:
        return CapabilityResult(
            capability_name="evidence.retrieve",
            ok=True,
            output=self.evidence,
            error=None,
            telemetry=None,
            artifacts=(),
        )


def _calculator_evidence_set(content: str) -> EvidenceSet:
    return EvidenceSet(
        evidence_set_id="live-provider-exec:evidence",
        query="fix calculator add",
        candidates=(
            EvidenceCandidate(
                candidate_id="live-provider-exec:candidate:calculator.py",
                file_path="calculator.py",
                symbol_id=None,
                span_start=1,
                span_end=max(1, len(content.splitlines())),
                content_hash=_content_hash(content),
                source_channels=("fixture",),
                bm25_score=None,
                vector_score=None,
                graph_score=None,
                retrieval_score=1.0,
                metadata={"case_id": "live-provider-exec"},
            ),
        ),
        diagnostics=RetrievalDiagnostics(
            bm25_count=1,
            vector_count=0,
            graph_added_count=0,
            precision_added_count=0,
            coverage_added_count=0,
            retrieval_disagreement=None,
            degraded=False,
            degradation_reason=None,
        ),
    )


def test_live_provider_can_return_bounded_edit_proposal_json() -> None:
    if os.getenv("HOMLLM_V4_RUN_LIVE_PROVIDER_SMOKE") != "1":
        pytest.skip("set HOMLLM_V4_RUN_LIVE_PROVIDER_SMOKE=1 to run live provider smoke")

    provider_name = os.getenv("HOMLLM_V4_LIVE_PROVIDER", "gemini")
    model = os.getenv("HOMLLM_V4_LIVE_MODEL", "gemini-3.5-flash-lite")
    api_key = os.getenv("HOMLLM_V4_LIVE_PROVIDER_API_KEY")
    adapter = build_v3_provider_edit_adapter(
        provider_name=provider_name,
        model=model,
        model_config=ModelConfig(temperature=0.0, max_output_tokens=1024),
        api_key=api_key,
    )
    proposer = ProviderBackedEditProposer(provider=adapter)

    result = proposer.propose(
        EditProposalRequest(
            task_id="live-provider-smoke",
            target_file="calculator.py",
            intent="fix add",
            expected_behavior="add returns a sum",
            current_content="def add(a, b):\n    return a - b\n",
            evidence_ids=("cand-1",),
            allowed_file_paths=("calculator.py",),
            verification_summary="python -m pytest . -q",
        )
    )

    if not result.ok:
        pytest.fail(f"live provider proposal failed: {result.error}")
    assert result.output is not None
    assert result.output.target_file == "calculator.py"
    assert "return a + b" in result.output.new_content
    assert result.output.evidence_ids == ("cand-1",)


def test_live_provider_patch_can_apply_and_verify_in_fixture_workspace(
    tmp_path: Path,
) -> None:
    if os.getenv("HOMLLM_V4_RUN_LIVE_PROVIDER_SMOKE") != "1":
        pytest.skip("set HOMLLM_V4_RUN_LIVE_PROVIDER_SMOKE=1 to run live provider smoke")

    provider_name = os.getenv("HOMLLM_V4_LIVE_PROVIDER", "gemini")
    model = os.getenv("HOMLLM_V4_LIVE_MODEL", "gemini-3.5-flash-lite")
    api_key = os.getenv("HOMLLM_V4_LIVE_PROVIDER_API_KEY")
    fixture_root = Path("fixtures/v4/python_patch_repo").resolve()
    workspace_root = tmp_path / "workspace"
    shutil.copytree(fixture_root, workspace_root)
    target_file = "calculator.py"
    current_content = (workspace_root / target_file).read_text(encoding="utf-8")

    adapter = build_v3_provider_edit_adapter(
        provider_name=provider_name,
        model=model,
        model_config=ModelConfig(temperature=0.0, max_output_tokens=2048),
        api_key=api_key,
    )
    planner = ProviderProposedPatchPlanner(
        retrieval_service=_FixtureRetrievalService(_calculator_evidence_set(current_content)),
        direct_read_service=DirectReadService(workspace_root=workspace_root),
        edit_proposer=ProviderBackedEditProposer(provider=adapter),
    )
    plan_result = planner.plan(
        ProviderProposedPatchPlanRequest(
            task_id="live-provider-exec",
            workspace_root=str(workspace_root),
            query="Fix calculator.add so it returns the sum instead of subtracting.",
            task_class="python_patch",
            index_id="live-provider-exec:fixture-index",
            target_file=target_file,
            intent="Fix calculator.add by changing subtraction to addition only.",
            expected_behavior="calculator.add(2, 3) returns 5 and existing pytest tests pass.",
            verification_argv=(sys.executable, "-m", "pytest", ".", "-q"),
            retrieval_policy={"intent": "PATCH", "top_k": 1},
            expected_content_hash=_content_hash(current_content),
        )
    )
    if not plan_result.ok:
        pytest.fail(f"live provider patch plan failed: {plan_result.error}")
    assert plan_result.output is not None

    manager = ArtifactManager(
        workspace_root=workspace_root,
        artifact_root=tmp_path / ".homllm" / "runs",
    )
    manager.create_run("live-provider-exec", {})
    loop = WriteVerifyLoop(
        patch_service=WorkspacePatchService(),
        command_service=LocalCommandService(
            policy=CommandPolicy(
                allowed_executables=(Path(sys.executable).name,),
                default_timeout_seconds=20,
                max_timeout_seconds=20,
            )
        ),
        artifact_manager=manager,
        event_writer=EventWriter(
            tmp_path / ".homllm" / "runs" / "live-provider-exec" / "events.jsonl"
        ),
    )

    result = loop.run(
        WriteVerifyLoopRequest(
            task_id="live-provider-exec",
            run_id="live-provider-exec",
            workspace_root=str(workspace_root),
            patch_request=plan_result.output.patch_request,
            verification_commands=(
                CommandRunRequest(
                    task_id="live-provider-exec",
                    workspace_root=str(workspace_root),
                    cwd=".",
                    argv=(sys.executable, "-m", "pytest", ".", "-q"),
                    timeout_seconds=20,
                ),
            ),
            max_verification_commands=1,
            max_patch_attempts=1,
            rollback_on_failure=True,
        )
    )

    assert result.stop_reason == "verified"
    assert "return a + b" in (workspace_root / target_file).read_text(encoding="utf-8")
