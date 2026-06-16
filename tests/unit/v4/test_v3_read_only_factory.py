import hashlib
import os
import shutil
import sys
from pathlib import Path

import pytest

from homllm_v4.adapters import v3_read_only_factory
from homllm_v4.adapters.v3_read_only_factory import build_v3_read_only_components
from homllm_v4.adapters.v3_provider_patch_factory import build_v3_provider_proposed_patch_planner
from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.command import CommandPolicy, CommandRunRequest
from homllm_v4.contracts.loop import ReadOnlyLoopRequest
from homllm_v4.contracts.policy import read_only_milestone1_policy
from homllm_v4.contracts.write_loop import WriteVerifyLoopRequest
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.planning.retrieval_patch_planner import (
    RetrievalBackedPatchPlanRequest,
    RetrievalBackedPatchPlanner,
)
from homllm_v4.planning.provider_edit_proposer import (
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
)
from homllm_v4.planning.provider_patch_planner import ProviderProposedPatchPlanRequest
from homllm_v4.registry.service_registry import ServiceRegistry
from homllm_v4.runtime.read_only_loop import ReadOnlyMultipassLoop
from homllm_v4.runtime.write_verify_loop import WriteVerifyLoop
from homllm_v4.services.direct_read_service import DirectReadService
from homllm_v4.services.context_service import ContextPackService
from homllm_v4.services.command_service import LocalCommandService
from homllm_v4.services.index_service import IndexService
from homllm_v4.services.patch_service import WorkspacePatchService
from homllm_v4.services.ranking_service import EvidenceRankingService
from homllm_v4.services.retrieval_service import EvidenceRetrievalService


class RecordingRetrievalPipeline:
    calls: list[dict[str, object]] = []

    def __init__(self, *args, **kwargs) -> None:
        self.__class__.calls.append({"args": args, "kwargs": kwargs})


class RecordingRankingPipeline:
    calls: list[dict[str, object]] = []

    def __init__(self, *args, **kwargs) -> None:
        self.__class__.calls.append({"args": args, "kwargs": kwargs})


class RecordingContextPipeline:
    calls: list[dict[str, object]] = []

    def __init__(self, *args, **kwargs) -> None:
        self.__class__.calls.append({"args": args, "kwargs": kwargs})


def clear_recorders() -> None:
    RecordingRetrievalPipeline.calls.clear()
    RecordingRankingPipeline.calls.clear()
    RecordingContextPipeline.calls.clear()


def normalized_content_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


class PromptAwareNoopProvider:
    def __init__(self, *, target_file: str, new_content: str) -> None:
        self.target_file = target_file
        self.new_content = new_content

    def propose_edit(self, request: ProviderEditProposalRequest) -> ProviderEditProposalResponse:
        import json

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
                    "rationale": "No-op real-index smoke proposal.",
                    "evidence_ids": list(evidence_ids),
                    "risk_flags": [],
                }
            ),
            tokens_in=1,
            tokens_out=1,
            model="fake",
            metadata={"provider": "prompt-aware-fake"},
        )


def test_factory_builds_registry_and_index_artifact_paths(monkeypatch) -> None:
    clear_recorders()
    monkeypatch.setattr(v3_read_only_factory, "RetrievalPipeline", RecordingRetrievalPipeline)
    monkeypatch.setattr(v3_read_only_factory, "RankingPipeline", RecordingRankingPipeline)
    monkeypatch.setattr(v3_read_only_factory, "ContextPipeline", RecordingContextPipeline)

    components = build_v3_read_only_components(
        Path("configs/agentic/ccg_stage2_canary_v1/ccg_stage2_agentic_ro3.yaml"),
        smoke_safe=True,
    )

    assert isinstance(components.service_registry, ServiceRegistry)
    assert isinstance(
        components.service_registry.get("index.validate", IndexService),
        IndexService,
    )
    assert isinstance(
        components.service_registry.get("evidence.retrieve", EvidenceRetrievalService),
        EvidenceRetrievalService,
    )
    assert isinstance(
        components.service_registry.get("evidence.rank", EvidenceRankingService),
        EvidenceRankingService,
    )
    assert isinstance(
        components.service_registry.get("context.build", ContextPackService),
        ContextPackService,
    )
    assert components.index_artifact_paths == {
        "duckdb": "indexes/metadata.duckdb",
        "tantivy": "indexes/bm25.index",
        "lancedb": "indexes/vectors.lance",
        "artifacts": "indexes",
    }
    assert RecordingRetrievalPipeline.calls[0]["kwargs"]["embedder"].dimension == 1024
    assert RecordingRetrievalPipeline.calls[0]["args"][0].parallel_search_enabled is False
    assert RecordingRankingPipeline.calls[0]["args"][0].reranker_enabled is False


@pytest.mark.skipif(
    os.environ.get("HOMLLM_V4_RUN_REAL_V3_SMOKE") != "1",
    reason="real v3 smoke is opt-in because it can touch local indexes and model runtimes",
)
def test_real_v3_read_only_loop_smoke(tmp_path: Path) -> None:
    components = build_v3_read_only_components(
        Path("configs/agentic/ccg_stage2_canary_v1/ccg_stage2_agentic_ro3.yaml"),
        smoke_safe=True,
    )
    manager = ArtifactManager(
        workspace_root=Path.cwd(),
        artifact_root=tmp_path / ".homllm" / "runs",
    )
    manager.create_run("real-smoke", {})
    writer = EventWriter(tmp_path / ".homllm" / "runs" / "real-smoke" / "events.jsonl")
    loop = ReadOnlyMultipassLoop(
        service_registry=components.service_registry,
        artifact_manager=manager,
        event_writer=writer,
        policy=read_only_milestone1_policy(),
    )

    result = loop.run(
        ReadOnlyLoopRequest(
            task_id="real-smoke-task",
            run_id="real-smoke",
            workspace_root=str(Path.cwd() / "test_repo"),
            query="How does admin search work?",
            max_passes=1,
            min_candidates=1,
            min_context_blocks=1,
            index_artifact_paths=components.index_artifact_paths,
        )
    )

    assert result.stop_reason in {"sufficient", "budget_exhausted", "empty_evidence"}
    assert result.pass_count == 1


@pytest.mark.skipif(
    os.environ.get("HOMLLM_V4_RUN_REAL_V3_SMOKE") != "1",
    reason="real v3 smoke is opt-in because it can touch local indexes and model runtimes",
)
def test_real_v3_retrieval_backed_patch_planner_smoke() -> None:
    repo_root = Path.cwd()
    workspace_root = repo_root / "test_repo"
    target_file = "api/routes.py"
    original = (workspace_root / target_file).read_text(encoding="utf-8")
    components = build_v3_read_only_components(
        Path("configs/agentic/ccg_stage2_canary_v1/ccg_stage2_agentic_ro3.yaml"),
        smoke_safe=True,
    )
    planner = RetrievalBackedPatchPlanner(
        retrieval_service=components.service_registry.get(
            "evidence.retrieve",
            EvidenceRetrievalService,
        ),
        direct_read_service=DirectReadService(workspace_root=workspace_root),
    )

    result = planner.plan(
        RetrievalBackedPatchPlanRequest(
            task_id="real-retrieval-plan",
            workspace_root=str(workspace_root),
            query="admin_search_endpoint in api routes",
            task_class="python_patch",
            index_id="idx",
            target_file=target_file,
            intent="plan a safe edit to admin search endpoint",
            expected_behavior="planner validates retrieval evidence before patching",
            new_content=original,
            verification_argv=("python", "-m", "pytest", ".", "-q"),
            retrieval_policy={"intent": "EXPLAIN", "top_k": 20},
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.patch_plan.target_files == (target_file,)
    assert result.output.patch_request.patches[0].file_path == target_file
    assert result.output.patch_request.patches[0].new_content == original


@pytest.mark.skipif(
    os.environ.get("HOMLLM_V4_RUN_REAL_V3_SMOKE") != "1",
    reason="real v3 smoke is opt-in because it can touch local indexes and model runtimes",
)
def test_real_v3_provider_proposed_patch_planner_smoke() -> None:
    repo_root = Path.cwd()
    workspace_root = repo_root / "test_repo"
    target_file = "api/routes.py"
    original = (workspace_root / target_file).read_text(encoding="utf-8")
    planner = build_v3_provider_proposed_patch_planner(
        config_path=Path("configs/agentic/ccg_stage2_canary_v1/ccg_stage2_agentic_ro3.yaml"),
        workspace_root=workspace_root,
        edit_provider=PromptAwareNoopProvider(
            target_file=target_file,
            new_content=original,
        ),
        smoke_safe=True,
    )

    result = planner.plan(
        ProviderProposedPatchPlanRequest(
            task_id="real-provider-proposed-plan",
            workspace_root=str(workspace_root),
            query="admin_search_endpoint in api routes",
            task_class="python_patch",
            index_id="idx",
            target_file=target_file,
            intent="plan a provider-proposed safe edit to admin search endpoint",
            expected_behavior="planner validates real retrieval evidence before provider patching",
            verification_argv=("python", "-m", "pytest", ".", "-q"),
            retrieval_policy={"intent": "EXPLAIN", "top_k": 20},
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.patch_plan.target_files == (target_file,)
    assert result.output.patch_plan.evidence_ids
    assert result.output.patch_request.patches[0].file_path == target_file
    assert result.output.patch_request.patches[0].new_content == original


@pytest.mark.skipif(
    os.environ.get("HOMLLM_V4_RUN_REAL_V3_SMOKE") != "1",
    reason="real v3 smoke is opt-in because it can touch local indexes and model runtimes",
)
def test_real_v3_provider_proposed_patch_execution_smoke(tmp_path: Path) -> None:
    repo_root = Path.cwd()
    source_workspace = repo_root / "test_repo"
    workspace_root = tmp_path / "workspace"
    shutil.copytree(source_workspace, workspace_root)
    target_file = "api/routes.py"
    original = (workspace_root / target_file).read_text(encoding="utf-8")
    planner = build_v3_provider_proposed_patch_planner(
        config_path=Path("configs/agentic/ccg_stage2_canary_v1/ccg_stage2_agentic_ro3.yaml"),
        workspace_root=workspace_root,
        edit_provider=PromptAwareNoopProvider(
            target_file=target_file,
            new_content=original,
        ),
        smoke_safe=True,
    )

    plan_result = planner.plan(
        ProviderProposedPatchPlanRequest(
            task_id="real-provider-proposed-exec",
            workspace_root=str(workspace_root),
            query="admin_search_endpoint in api routes",
            task_class="python_patch",
            index_id="idx",
            target_file=target_file,
            intent="execute a provider-proposed no-op edit to admin search endpoint safely",
            expected_behavior="real indexed retrieval feeds provider patch execution and verification",
            verification_argv=(sys.executable, "-m", "compileall", "-q", "api/routes.py"),
            retrieval_policy={"intent": "EXPLAIN", "top_k": 20},
            expected_content_hash=normalized_content_hash(original),
        )
    )
    assert plan_result.ok is True
    assert plan_result.output is not None

    manager = ArtifactManager(
        workspace_root=workspace_root,
        artifact_root=tmp_path / ".homllm" / "runs",
    )
    manager.create_run("real-provider-exec-smoke", {})
    loop = WriteVerifyLoop(
        patch_service=WorkspacePatchService(),
        command_service=LocalCommandService(
            policy=CommandPolicy(
                allowed_executables=(Path(sys.executable).name,),
                default_timeout_seconds=10,
                max_timeout_seconds=10,
            )
        ),
        artifact_manager=manager,
        event_writer=EventWriter(
            tmp_path / ".homllm" / "runs" / "real-provider-exec-smoke" / "events.jsonl"
        ),
    )

    result = loop.run(
        WriteVerifyLoopRequest(
            task_id="real-provider-proposed-exec",
            run_id="real-provider-exec-smoke",
            workspace_root=str(workspace_root),
            patch_request=plan_result.output.patch_request,
            verification_commands=(
                CommandRunRequest(
                    task_id="real-provider-proposed-exec",
                    workspace_root=str(workspace_root),
                    cwd=".",
                    argv=(sys.executable, "-m", "compileall", "-q", "api/routes.py"),
                    timeout_seconds=10,
                ),
            ),
            max_verification_commands=1,
            max_patch_attempts=1,
            rollback_on_failure=True,
        )
    )

    assert result.stop_reason == "verified"
    assert result.patch_attempt_count == 1
    assert result.patch_result is not None
    assert result.patch_result.applied is True
    assert len(result.verification_results) == 1
    assert result.verification_results[0].exit_code == 0
    assert (workspace_root / target_file).read_text(encoding="utf-8") == original
    assert (source_workspace / target_file).read_text(encoding="utf-8") == original
