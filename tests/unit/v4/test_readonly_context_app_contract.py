from pathlib import Path

from homllm_v4.app.readonly_context_app import build_readonly_context
from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.context import ContextBlock, ContextPack
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import (
    EvidenceCandidate,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.contracts.index import (
    IndexFreshness,
    IndexValidation,
    RepoIndexManifest,
)
from homllm_v4.contracts.policy import read_only_milestone1_policy
from homllm_v4.contracts.ranking import (
    RankedEvidence,
    RankedEvidenceSet,
    RankingDiagnostics,
)
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.registry.service_registry import ServiceRegistry
from homllm_v4.services.context_service import ContextPackService
from homllm_v4.services.index_service import IndexService
from homllm_v4.services.ranking_service import EvidenceRankingService
from homllm_v4.services.retrieval_service import EvidenceRetrievalService


def telemetry() -> CapabilityTelemetry:
    return CapabilityTelemetry(
        started_at="",
        ended_at="",
        duration_ms=1,
        input_summary={},
        output_summary={},
        token_usage={},
        model_usage={},
        degraded=False,
        degradation_reason=None,
    )


class FakeIndexService(IndexService):
    def validate(self, request):
        manifest = RepoIndexManifest(
            index_id="idx",
            workspace_root=request.workspace_root,
            schema_version="test",
            created_at="0",
            last_indexed_at="0",
            source_file_count=1,
            chunk_count=1,
            symbol_count=0,
            relation_count=0,
            embedding_model="none",
            embedding_dimension=0,
            artifact_paths={},
            ignored_paths_summary={},
            warnings=(),
        )
        freshness = IndexFreshness("fresh", None, "0", False, 0, 0)
        return CapabilityResult("index.validate", True, IndexValidation(manifest, freshness), None, telemetry(), ())


class FailingIndexService(IndexService):
    def validate(self, request):
        return CapabilityResult(
            "index.validate",
            False,
            None,
            CapabilityError("index_missing", "missing", True, False, {}),
            telemetry(),
            (),
        )


class FakeRetrievalService(EvidenceRetrievalService):
    def retrieve(self, request):
        candidate = EvidenceCandidate(
            candidate_id="c1",
            file_path="src/demo.py",
            symbol_id=None,
            span_start=1,
            span_end=1,
            content_hash="hash",
            source_channels=("bm25",),
            bm25_score=1.0,
            vector_score=None,
            graph_score=None,
            retrieval_score=1.0,
            metadata={},
        )
        diagnostics = RetrievalDiagnostics(1, 0, 0, 0, 0, None, False, None)
        return CapabilityResult(
            "evidence.retrieve",
            True,
            EvidenceSet("es1", request.query, (candidate,), diagnostics),
            None,
            telemetry(),
            (),
        )


class EmptyRetrievalService(EvidenceRetrievalService):
    def retrieve(self, request):
        diagnostics = RetrievalDiagnostics(0, 0, 0, 0, 0, None, False, None)
        return CapabilityResult(
            "evidence.retrieve",
            True,
            EvidenceSet("es1", request.query, (), diagnostics),
            None,
            telemetry(),
            (),
        )


class FakeRankingService(EvidenceRankingService):
    def rank(self, request):
        item = RankedEvidence(request.evidence_set.candidates[0], 1, 1.0, {"bm25": 1.0}, False)
        diagnostics = RankingDiagnostics(False, False, None, None, None, {"bm25": 1})
        return CapabilityResult(
            "evidence.rank",
            True,
            RankedEvidenceSet("rs1", (item,), diagnostics),
            None,
            telemetry(),
            (),
        )


class FakeContextService(ContextPackService):
    def build(self, request):
        block = ContextBlock("b1", "c1", "src/demo.py", 1, 1, "print('x')", 3, 1.0, "src/demo.py:1")
        pack = ContextPack("ctx1", "answer", "print('x')", (block,), 3, (), {"ok": True})
        return CapabilityResult("context.build", True, pack, None, telemetry(), ())


def registry(index_service=None, retrieval_service=None) -> ServiceRegistry:
    reg = ServiceRegistry()
    reg.register("index.validate", index_service or FakeIndexService())
    reg.register("evidence.retrieve", retrieval_service or FakeRetrievalService())
    reg.register("evidence.rank", FakeRankingService())
    reg.register("context.build", FakeContextService())
    return reg


def app_deps(tmp_path: Path):
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("run-1", {})
    writer = EventWriter(tmp_path / ".homllm" / "runs" / "run-1" / "events.jsonl")
    return manager, writer


def test_app_executes_services_and_returns_context(tmp_path: Path) -> None:
    manager, writer = app_deps(tmp_path)

    result = build_readonly_context(
        task_id="task-1",
        run_id="run-1",
        workspace_root=str(tmp_path),
        query="explain demo",
        service_registry=registry(),
        artifact_manager=manager,
        event_writer=writer,
        policy=read_only_milestone1_policy(),
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.text == "print('x')"
    events = (tmp_path / ".homllm" / "runs" / "run-1" / "events.jsonl").read_text(encoding="utf-8")
    assert "run_started" in events
    assert "index_validated" in events
    assert "retrieval_completed" in events
    assert "ranking_completed" in events
    assert "context_completed" in events
    assert "run_completed" in events


def test_app_stops_on_index_failure(tmp_path: Path) -> None:
    manager, writer = app_deps(tmp_path)

    result = build_readonly_context(
        task_id="task-1",
        run_id="run-1",
        workspace_root=str(tmp_path),
        query="explain demo",
        service_registry=registry(index_service=FailingIndexService()),
        artifact_manager=manager,
        event_writer=writer,
        policy=read_only_milestone1_policy(),
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "index_missing"


def test_app_stops_on_empty_evidence(tmp_path: Path) -> None:
    manager, writer = app_deps(tmp_path)

    result = build_readonly_context(
        task_id="task-1",
        run_id="run-1",
        workspace_root=str(tmp_path),
        query="explain demo",
        service_registry=registry(retrieval_service=EmptyRetrievalService()),
        artifact_manager=manager,
        event_writer=writer,
        policy=read_only_milestone1_policy(),
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "empty_evidence_set"
