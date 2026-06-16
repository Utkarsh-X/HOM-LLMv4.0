from homllm.context.interfaces import ContextArtifact, ContextBlock as V3ContextBlock
from homllm.common.types import Intent
from homllm.ranking.interfaces import DebugTrace, RankMetadata, RankingOutput
from homllm.retrieval.interfaces import Candidate, RetrievalResult

from homllm_v4.adapters.v3_context_adapter import V3ContextAdapter
from homllm_v4.adapters.v3_ranking_adapter import V3RankingAdapter
from homllm_v4.adapters.v3_retrieval_adapter import V3RetrievalAdapter
from homllm_v4.contracts.context import ContextPackRequest
from homllm_v4.contracts.evidence import EvidenceRetrievalRequest
from homllm_v4.contracts.ranking import RankedEvidence, RankedEvidenceSet, RankingDiagnostics
from homllm_v4.contracts.ranking import EvidenceRankingRequest
from homllm_v4.services.context_service import ContextPackService
from homllm_v4.services.ranking_service import EvidenceRankingService
from homllm_v4.services.retrieval_service import EvidenceRetrievalService


class FakeRetrievalPipeline:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def retrieve(self, query, intent, top_k):
        self.calls.append({"query": query, "intent": intent, "top_k": top_k})
        return RetrievalResult(
            candidates=[
                Candidate(
                    doc_id="doc-1",
                    file="src/demo.py",
                    symbol_id="Demo.run",
                    content="def run():\n    return 1\n",
                    bm25_score=0.7,
                    vector_score=0.2,
                    hybrid_score=0.9,
                    provenance=("bm25", "vector"),
                    span_start=10,
                    span_end=12,
                )
            ],
            query_id="query-1",
            metadata={
                "bm25_count": 3,
                "vector_count": 2,
                "precision_recovery_added": 1,
                "coverage_recovery_added": 0,
                "graph_stitch_status": "disabled_config_off",
            },
        )


class FakeRankingPipeline:
    def __init__(self) -> None:
        self.last_input = None

    def rank(self, input_data):
        self.last_input = input_data
        candidate = input_data.candidates[0]
        trace = DebugTrace(
            candidate_id=candidate.doc_id,
            base_score=0.5,
            rerank_score=0.4,
            struct_bonus=0.1,
            final_score=1.0,
            features=None,
            provenance=candidate.provenance,
            rerank_evaluated=True,
        )
        return RankingOutput(
            ranked_candidates=(candidate,),
            debug_traces=(trace,),
            metadata=RankMetadata(
                latency_ms=12,
                reranker_used=True,
                reranker_unavailable=False,
                candidate_count=1,
                ranking_concentration={"max_file_block_ratio": 1.0},
                ranking_geometry={"score_separation": 0.25},
            ),
        )


class FakeContextPipeline:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def assemble(self, ranking_output, query, query_id=None, unresolved_claim_hints=None):
        self.calls.append(
            {
                "query": query,
                "query_id": query_id,
                "candidate_count": len(ranking_output.ranked_candidates),
                "hints": unresolved_claim_hints,
            }
        )
        return ContextArtifact(
            query_id=query_id or "generated-query-id",
            context_text="src/demo.py:10\n\ndef run():\n    return 1",
            blocks=(
                V3ContextBlock(
                    block_id="doc-1",
                    file="src/demo.py",
                    start_line=10,
                    end_line=12,
                    content="def run():\n    return 1\n",
                    symbol_id="Demo.run",
                    symbol_name="Demo.run",
                    provenance=("bm25",),
                ),
            ),
            token_budget=100,
            used_tokens=9,
            provenance={"selected": ["doc-1"]},
            explain_trace=("selected top ranked block",),
        )


def test_retrieval_adapter_maps_v4_request_to_v3_pipeline_and_back() -> None:
    pipeline = FakeRetrievalPipeline()
    adapter = V3RetrievalAdapter(pipeline=pipeline)

    result = adapter.retrieve(
        EvidenceRetrievalRequest(
            task_id="task-1",
            query="explain run",
            task_class="answer",
            index_id="idx",
            policy={"intent": "EXPLAIN", "top_k": 5},
        )
    )

    assert pipeline.calls == [{"query": "explain run", "intent": Intent.EXPLAIN, "top_k": 5}]
    assert result.evidence_set_id == "query-1"
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.candidate_id == "doc-1"
    assert candidate.file_path == "src/demo.py"
    assert candidate.symbol_id == "Demo.run"
    assert candidate.span_start == 10
    assert candidate.span_end == 12
    assert candidate.metadata["content"] == "def run():\n    return 1\n"
    assert result.diagnostics.bm25_count == 3
    assert result.diagnostics.vector_count == 2
    assert result.diagnostics.precision_added_count == 1


def test_ranking_adapter_reconstructs_v3_candidates_and_maps_scores() -> None:
    retrieval = V3RetrievalAdapter(pipeline=FakeRetrievalPipeline()).retrieve(
        EvidenceRetrievalRequest(
            task_id="task-1",
            query="explain run",
            task_class="answer",
            index_id="idx",
            policy={"top_k": 5},
        )
    )
    pipeline = FakeRankingPipeline()
    adapter = V3RankingAdapter(pipeline=pipeline)

    result = adapter.rank(
        EvidenceRankingRequest(
            task_id="task-1",
            evidence_set=retrieval,
            policy={"reranker_enabled": True},
        )
    )

    assert pipeline.last_input is not None
    assert pipeline.last_input.query == "explain run"
    assert pipeline.last_input.candidates[0].content == "def run():\n    return 1\n"
    assert len(result.items) == 1
    item = result.items[0]
    assert item.rank == 1
    assert item.final_score == 1.0
    assert item.reranked is True
    assert item.score_components == {
        "base": 0.5,
        "rerank": 0.4,
        "struct": 0.1,
    }
    assert result.diagnostics.reranker_used is True
    assert result.diagnostics.reranker_available is True
    assert result.diagnostics.concentration_ratio == 1.0
    assert result.diagnostics.score_separation == 0.25


def test_context_adapter_reconstructs_v3_ranking_output_and_maps_context_pack() -> None:
    candidate = V3RetrievalAdapter(pipeline=FakeRetrievalPipeline()).retrieve(
        EvidenceRetrievalRequest(
            task_id="task-1",
            query="explain run",
            task_class="answer",
            index_id="idx",
            policy={"top_k": 5},
        )
    ).candidates[0]
    ranked = RankedEvidenceSet(
        ranked_set_id="ranked-1",
        items=(
            RankedEvidence(
                candidate=candidate,
                rank=1,
                final_score=1.0,
                score_components={"base": 0.5, "rerank": 0.4, "struct": 0.1},
                reranked=True,
            ),
        ),
        diagnostics=RankingDiagnostics(
            reranker_used=True,
            reranker_available=True,
            reranker_degraded_reason=None,
            concentration_ratio=1.0,
            score_separation=0.25,
            top_source_channels={"bm25": 1},
        ),
    )
    pipeline = FakeContextPipeline()
    adapter = V3ContextAdapter(pipeline=pipeline)

    result = adapter.build(
        ContextPackRequest(
            task_id="task-1",
            ranked_evidence_set=ranked,
            policy={"unresolved_claim_hints": ["missing retry path"]},
            query="explain run",
        )
    )

    assert pipeline.calls == [
        {
            "query": "explain run",
            "query_id": "ranked-1",
            "candidate_count": 1,
            "hints": ["missing retry path"],
        }
    ]
    assert result.context_pack_id == "ranked-1"
    assert result.text.startswith("src/demo.py:10")
    assert result.used_tokens == 9
    assert len(result.blocks) == 1
    assert result.blocks[0].candidate_id == "doc-1"
    assert result.blocks[0].citation == "src/demo.py:10-12"
    assert result.diagnostics["provenance"] == {"selected": ["doc-1"]}


def test_retrieval_service_wraps_adapter_result_in_capability_result() -> None:
    request = EvidenceRetrievalRequest(
        task_id="task-1",
        query="explain run",
        task_class="answer",
        index_id="idx",
        policy={"top_k": 5},
    )
    service = EvidenceRetrievalService(
        adapter=V3RetrievalAdapter(pipeline=FakeRetrievalPipeline())
    )

    result = service.retrieve(request)

    assert result.ok is True
    assert result.output is not None
    assert result.output.query == "explain run"
    assert result.telemetry.output_summary["candidate_count"] == 1


def test_ranking_service_wraps_adapter_result_in_capability_result() -> None:
    evidence = V3RetrievalAdapter(pipeline=FakeRetrievalPipeline()).retrieve(
        EvidenceRetrievalRequest(
            task_id="task-1",
            query="explain run",
            task_class="answer",
            index_id="idx",
            policy={"top_k": 5},
        )
    )
    service = EvidenceRankingService(adapter=V3RankingAdapter(pipeline=FakeRankingPipeline()))

    result = service.rank(
        EvidenceRankingRequest(task_id="task-1", evidence_set=evidence, policy={})
    )

    assert result.ok is True
    assert result.output is not None
    assert len(result.output.items) == 1
    assert result.telemetry.output_summary["item_count"] == 1


def test_context_service_wraps_adapter_result_in_capability_result() -> None:
    evidence = V3RetrievalAdapter(pipeline=FakeRetrievalPipeline()).retrieve(
        EvidenceRetrievalRequest(
            task_id="task-1",
            query="explain run",
            task_class="answer",
            index_id="idx",
            policy={"top_k": 5},
        )
    )
    ranked = V3RankingAdapter(pipeline=FakeRankingPipeline()).rank(
        EvidenceRankingRequest(task_id="task-1", evidence_set=evidence, policy={})
    )
    service = ContextPackService(adapter=V3ContextAdapter(pipeline=FakeContextPipeline()))

    result = service.build(
        ContextPackRequest(
            task_id="task-1",
            ranked_evidence_set=ranked,
            policy={},
            query="explain run",
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.used_tokens == 9
    assert result.telemetry.output_summary["block_count"] == 1
