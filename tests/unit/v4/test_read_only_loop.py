import json
from pathlib import Path

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.context import ContextBlock, ContextPack
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import (
    EvidenceCandidate,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.contracts.index import IndexFreshness, IndexValidation, RepoIndexManifest
from homllm_v4.contracts.policy import read_only_milestone1_policy
from homllm_v4.contracts.ranking import RankedEvidence, RankedEvidenceSet, RankingDiagnostics
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.registry.service_registry import ServiceRegistry
from homllm_v4.runtime.read_only_loop import ReadOnlyMultipassLoop
from homllm_v4.runtime.repetition_guard import candidate_overlap_ratio, is_repeated_retrieval
from homllm_v4.runtime.sufficiency import DeterministicSufficiencyChecker
from homllm_v4.contracts.loop import ReadOnlyLoopRequest
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


def candidate(candidate_id: str, file_path: str = "src/demo.py") -> EvidenceCandidate:
    return EvidenceCandidate(
        candidate_id=candidate_id,
        file_path=file_path,
        symbol_id=None,
        span_start=1,
        span_end=3,
        content_hash=f"hash-{candidate_id}",
        source_channels=("bm25",),
        bm25_score=1.0,
        vector_score=None,
        graph_score=None,
        retrieval_score=1.0,
        metadata={"content": f"content for {candidate_id}"},
    )


def evidence_set(ids: tuple[str, ...], query: str = "explain demo") -> EvidenceSet:
    return EvidenceSet(
        evidence_set_id=f"evidence-{len(ids)}-{'-'.join(ids)}",
        query=query,
        candidates=tuple(candidate(candidate_id) for candidate_id in ids),
        diagnostics=RetrievalDiagnostics(
            bm25_count=len(ids),
            vector_count=0,
            graph_added_count=0,
            precision_added_count=0,
            coverage_added_count=0,
            retrieval_disagreement=None,
            degraded=False,
            degradation_reason=None,
        ),
    )


def ranked_set(evidence: EvidenceSet) -> RankedEvidenceSet:
    return RankedEvidenceSet(
        ranked_set_id=f"{evidence.evidence_set_id}:ranked",
        items=tuple(
            RankedEvidence(
                candidate=item,
                rank=index,
                final_score=1.0,
                score_components={"base": 1.0, "rerank": 0.0, "struct": 0.0},
                reranked=False,
            )
            for index, item in enumerate(evidence.candidates, start=1)
        ),
        diagnostics=RankingDiagnostics(
            reranker_used=False,
            reranker_available=False,
            reranker_degraded_reason=None,
            concentration_ratio=None,
            score_separation=None,
            top_source_channels={"bm25": len(evidence.candidates)},
        ),
    )


def context_pack(ranked: RankedEvidenceSet) -> ContextPack:
    return ContextPack(
        context_pack_id=f"{ranked.ranked_set_id}:context",
        purpose="answer",
        text="\n".join(item.candidate.metadata["content"] for item in ranked.items),
        blocks=tuple(
            ContextBlock(
                block_id=item.candidate.candidate_id,
                candidate_id=item.candidate.candidate_id,
                file_path=item.candidate.file_path,
                span_start=item.candidate.span_start,
                span_end=item.candidate.span_end,
                text=str(item.candidate.metadata["content"]),
                token_count=4,
                score=item.final_score,
                citation=f"{item.candidate.file_path}:1-3",
            )
            for item in ranked.items
        ),
        used_tokens=4 * len(ranked.items),
        dropped_candidates=(),
        diagnostics={},
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
        return CapabilityResult(
            "index.validate",
            True,
            IndexValidation(manifest, IndexFreshness("fresh", None, "0", False, 0, 0)),
            None,
            telemetry(),
            (),
        )


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


class SequenceRetrievalService(EvidenceRetrievalService):
    def __init__(self, sets: tuple[EvidenceSet, ...]) -> None:
        self.sets = sets
        self.calls = 0

    def retrieve(self, request):
        evidence = self.sets[min(self.calls, len(self.sets) - 1)]
        self.calls += 1
        return CapabilityResult("evidence.retrieve", True, evidence, None, telemetry(), ())


class FakeRankingService(EvidenceRankingService):
    def rank(self, request):
        return CapabilityResult(
            "evidence.rank",
            True,
            ranked_set(request.evidence_set),
            None,
            telemetry(),
            (),
        )


class FakeContextService(ContextPackService):
    def build(self, request):
        return CapabilityResult(
            "context.build",
            True,
            context_pack(request.ranked_evidence_set),
            None,
            telemetry(),
            (),
        )


def registry(index_service=None, retrieval_service=None) -> ServiceRegistry:
    reg = ServiceRegistry()
    reg.register("index.validate", index_service or FakeIndexService())
    reg.register("evidence.retrieve", retrieval_service or SequenceRetrievalService((evidence_set(("a", "b")),)))
    reg.register("evidence.rank", FakeRankingService())
    reg.register("context.build", FakeContextService())
    return reg


def loop_deps(tmp_path: Path, reg: ServiceRegistry) -> ReadOnlyMultipassLoop:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("run-1", {})
    writer = EventWriter(tmp_path / ".homllm" / "runs" / "run-1" / "events.jsonl")
    return ReadOnlyMultipassLoop(
        service_registry=reg,
        artifact_manager=manager,
        event_writer=writer,
        policy=read_only_milestone1_policy(),
    )


def request(tmp_path: Path, max_passes: int = 3) -> ReadOnlyLoopRequest:
    return ReadOnlyLoopRequest(
        task_id="task-1",
        run_id="run-1",
        workspace_root=str(tmp_path),
        query="explain demo",
        max_passes=max_passes,
        min_candidates=2,
        min_context_blocks=2,
    )


def test_sufficiency_checker_reports_missing_reasons() -> None:
    decision = DeterministicSufficiencyChecker().check(
        evidence_set=evidence_set(("a",)),
        context_pack=context_pack(ranked_set(evidence_set(("a",)))),
        min_candidates=2,
        min_context_blocks=2,
    )

    assert decision.sufficient is False
    assert decision.score < 1.0
    assert "insufficient_candidates" in decision.missing_reasons
    assert "insufficient_context_blocks" in decision.missing_reasons


def test_repetition_guard_uses_candidate_overlap_and_sufficiency_progress() -> None:
    previous = evidence_set(tuple(f"c{i}" for i in range(20)))
    current = evidence_set(tuple(f"c{i}" for i in range(16)) + tuple(f"n{i}" for i in range(4)))

    assert candidate_overlap_ratio(previous, current, top_n=20) == 0.8
    assert is_repeated_retrieval(
        previous,
        current,
        previous_sufficiency_score=0.5,
        current_sufficiency_score=0.5,
        threshold=0.8,
    ) is True
    assert is_repeated_retrieval(
        previous,
        current,
        previous_sufficiency_score=0.5,
        current_sufficiency_score=0.7,
        threshold=0.8,
    ) is False


def test_loop_stops_when_sufficient_and_builds_claim_support(tmp_path: Path) -> None:
    loop = loop_deps(tmp_path, registry())

    result = loop.run(request(tmp_path))

    assert result.stop_reason == "sufficient"
    assert result.pass_count == 1
    assert result.sufficiency.sufficient is True
    assert result.context_pack is not None
    assert result.claim_support
    assert result.claim_support[0].evidence_ids == ("a",)
    assert "Evidence-backed context is ready" in result.response_text
    artifact_path = tmp_path / ".homllm" / "runs" / "run-1" / "response" / "read_only_loop_result.json"
    assert artifact_path.is_file()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["stop_reason"] == "sufficient"
    assert payload["sufficiency"]["sufficient"] is True
    assert payload["claim_support"][0]["evidence_ids"] == ["a"]


def test_loop_stops_on_repeated_state(tmp_path: Path) -> None:
    repeated = SequenceRetrievalService(
        (
            evidence_set(tuple(f"c{i}" for i in range(20))),
            evidence_set(tuple(f"c{i}" for i in range(16)) + tuple(f"n{i}" for i in range(4))),
        )
    )
    loop = loop_deps(tmp_path, registry(retrieval_service=repeated))

    repeated_request = request(tmp_path, max_passes=3)
    repeated_request = ReadOnlyLoopRequest(
        task_id=repeated_request.task_id,
        run_id=repeated_request.run_id,
        workspace_root=repeated_request.workspace_root,
        query=repeated_request.query,
        max_passes=repeated_request.max_passes,
        min_candidates=25,
        min_context_blocks=25,
    )

    result = loop.run(repeated_request)

    assert result.stop_reason == "repeated_state"
    assert result.pass_count == 2
    assert result.sufficiency.sufficient is False


def test_loop_stops_on_budget_exhaustion(tmp_path: Path) -> None:
    thin = SequenceRetrievalService((evidence_set(("only-one",)), evidence_set(("still-one",))))
    loop = loop_deps(tmp_path, registry(retrieval_service=thin))

    result = loop.run(request(tmp_path, max_passes=2))

    assert result.stop_reason == "budget_exhausted"
    assert result.pass_count == 2
    assert result.sufficiency.sufficient is False


def test_loop_stops_on_service_failure(tmp_path: Path) -> None:
    loop = loop_deps(tmp_path, registry(index_service=FailingIndexService()))

    result = loop.run(request(tmp_path))

    assert result.stop_reason == "service_failed"
    assert result.error is not None
    assert result.error.code == "index_missing"
    assert result.sufficiency.sufficient is False
