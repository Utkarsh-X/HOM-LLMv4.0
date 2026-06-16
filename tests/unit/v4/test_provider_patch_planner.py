import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.evidence import (
    EvidenceCandidate,
    EvidenceRetrievalRequest,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.planning.provider_edit_proposer import (
    ProviderBackedEditProposer,
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
)
from homllm_v4.planning.provider_patch_planner import (
    ProviderProposedPatchPlanRequest,
    ProviderProposedPatchPlanner,
)
from homllm_v4.services.direct_read_service import DirectReadService


def content_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def evidence_set() -> EvidenceSet:
    content = "def add(a, b):\n    return a - b\n"
    return EvidenceSet(
        evidence_set_id="evidence-1",
        query="fix add",
        candidates=(
            EvidenceCandidate(
                candidate_id="cand-1",
                file_path="calculator.py",
                symbol_id=None,
                span_start=1,
                span_end=2,
                content_hash=content_hash(content),
                source_channels=("bm25",),
                bm25_score=1.0,
                vector_score=None,
                graph_score=None,
                retrieval_score=1.0,
                metadata={"content": "retrieved evidence chunk for add"},
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


class FakeRetrievalService:
    def __init__(self, output: EvidenceSet | None = None) -> None:
        self.output = output or evidence_set()
        self.last_request: EvidenceRetrievalRequest | None = None

    def retrieve(self, request: EvidenceRetrievalRequest) -> CapabilityResult[EvidenceSet]:
        self.last_request = request
        return CapabilityResult(
            capability_name="evidence.retrieve",
            ok=True,
            output=self.output,
            error=None,
            telemetry=None,
            artifacts=(),
        )


@dataclass
class FakeProvider:
    response_text: str
    last_request: ProviderEditProposalRequest | None = None

    def propose_edit(self, request: ProviderEditProposalRequest) -> ProviderEditProposalResponse:
        self.last_request = request
        return ProviderEditProposalResponse(
            text=self.response_text,
            tokens_in=13,
            tokens_out=9,
            model="fake-model",
            metadata={"provider": "fake"},
        )


def request(
    tmp_path: Path,
    *,
    target_file: str | None = "calculator.py",
) -> ProviderProposedPatchPlanRequest:
    original = "def add(a, b):\n    return a - b\n"
    if target_file is not None:
        (tmp_path / target_file).write_text(original, encoding="utf-8")
    return ProviderProposedPatchPlanRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        query="fix add",
        task_class="python_patch",
        index_id="idx",
        target_file=target_file,
        intent="fix add",
        expected_behavior="add returns a sum",
        verification_argv=(sys.executable, "-m", "pytest", ".", "-q"),
        retrieval_policy={"intent": "EXPLAIN", "top_k": 5},
        expected_content_hash=content_hash(original),
    )


def test_provider_proposed_patch_planner_creates_patch_plan_from_retrieval_and_provider(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use addition.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    planner = ProviderProposedPatchPlanner(
        retrieval_service=FakeRetrievalService(),
        direct_read_service=DirectReadService(workspace_root=tmp_path),
        edit_proposer=ProviderBackedEditProposer(provider=provider),
    )

    result = planner.plan(request(tmp_path))

    assert result.ok is True
    assert result.output is not None
    assert result.output.patch_plan.target_files == ("calculator.py",)
    assert result.output.patch_plan.evidence_ids == ("cand-1",)
    assert result.output.patch_request.patches[0].file_path == "calculator.py"
    assert "return a + b" in result.output.patch_request.patches[0].new_content
    assert result.output.verification_commands[0].argv == (sys.executable, "-m", "pytest", ".", "-q")
    assert provider.last_request is not None
    assert "def add(a, b)" in provider.last_request.prompt
    assert result.telemetry.output_summary["target_selection_decision"] == "supplied"
    assert result.telemetry.output_summary["resolved_target_file"] == "calculator.py"
    assert result.telemetry.output_summary["prompt_char_count"] > 0
    assert result.telemetry.output_summary["evidence_context_item_count"] == 1
    assert result.telemetry.output_summary["evidence_context_rendered_char_count"] > 0
    assert result.telemetry.output_summary["evidence_context_truncated"] is False


def test_provider_proposed_patch_planner_selects_target_file_from_retrieved_evidence(
    tmp_path: Path,
) -> None:
    original = "def add(a, b):\n    return a - b\n"
    (tmp_path / "calculator.py").write_text(original, encoding="utf-8")
    retrieval = FakeRetrievalService()
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use addition.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    planner = ProviderProposedPatchPlanner(
        retrieval_service=retrieval,
        direct_read_service=DirectReadService(workspace_root=tmp_path),
        edit_proposer=ProviderBackedEditProposer(provider=provider),
    )

    result = planner.plan(request(tmp_path, target_file=None))

    assert result.ok is True
    assert result.output is not None
    assert result.output.patch_request.patches[0].file_path == "calculator.py"
    assert retrieval.last_request is not None
    assert retrieval.last_request.target_files == ()
    assert result.telemetry.output_summary["target_selection_decision"] == "selected"
    assert result.telemetry.output_summary["resolved_target_file"] == "calculator.py"
    assert result.telemetry.output_summary["candidate_file_scores"] == {"calculator.py": 1.0}


def test_provider_proposed_patch_planner_passes_retrieved_evidence_context_to_provider(
    tmp_path: Path,
) -> None:
    original = "def add(a, b):\n    return a - b\n"
    (tmp_path / "calculator.py").write_text(original, encoding="utf-8")
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use retrieved context.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    planner = ProviderProposedPatchPlanner(
        retrieval_service=FakeRetrievalService(output=evidence_set()),
        direct_read_service=DirectReadService(workspace_root=tmp_path),
        edit_proposer=ProviderBackedEditProposer(provider=provider),
    )

    result = planner.plan(request(tmp_path))

    assert result.ok is True
    assert provider.last_request is not None
    assert "retrieved evidence chunk for add" in provider.last_request.prompt


def test_provider_proposed_patch_planner_passes_repair_context_to_provider(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Repair verification failure.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    planner = ProviderProposedPatchPlanner(
        retrieval_service=FakeRetrievalService(),
        direct_read_service=DirectReadService(workspace_root=tmp_path),
        edit_proposer=ProviderBackedEditProposer(provider=provider),
    )
    plan_request = request(tmp_path)
    plan_request = ProviderProposedPatchPlanRequest(
        task_id=plan_request.task_id,
        workspace_root=plan_request.workspace_root,
        query=plan_request.query,
        task_class=plan_request.task_class,
        index_id=plan_request.index_id,
        target_file=plan_request.target_file,
        intent=plan_request.intent,
        expected_behavior=plan_request.expected_behavior,
        verification_argv=plan_request.verification_argv,
        retrieval_policy=plan_request.retrieval_policy,
        expected_content_hash=plan_request.expected_content_hash,
        repair_context="Previous verification failed with exit_code=1.",
    )

    result = planner.plan(plan_request)

    assert result.ok is True
    assert provider.last_request is not None
    assert "Repair context: Previous verification failed with exit_code=1." in (
        provider.last_request.prompt
    )


def test_provider_proposed_patch_planner_preserves_original_trailing_newline(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b",'
            '"rationale":"Use addition.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    planner = ProviderProposedPatchPlanner(
        retrieval_service=FakeRetrievalService(),
        direct_read_service=DirectReadService(workspace_root=tmp_path),
        edit_proposer=ProviderBackedEditProposer(provider=provider),
    )

    result = planner.plan(request(tmp_path))

    assert result.ok is True
    assert result.output is not None
    assert result.output.patch_request.patches[0].new_content.endswith("\n")


def test_provider_proposed_patch_planner_stops_before_provider_when_target_selection_ambiguous(
    tmp_path: Path,
) -> None:
    (tmp_path / "calculator.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "helpers.py").write_text("def helper():\n    return None\n", encoding="utf-8")
    ambiguous = EvidenceSet(
        evidence_set_id="evidence-ambiguous",
        query="fix add",
        candidates=(
            EvidenceCandidate(
                candidate_id="cand-1",
                file_path="calculator.py",
                symbol_id=None,
                span_start=1,
                span_end=2,
                content_hash="hash",
                source_channels=("bm25",),
                bm25_score=0.6,
                vector_score=None,
                graph_score=None,
                retrieval_score=0.6,
                metadata={},
            ),
            EvidenceCandidate(
                candidate_id="cand-2",
                file_path="helpers.py",
                symbol_id=None,
                span_start=1,
                span_end=2,
                content_hash="hash",
                source_channels=("bm25",),
                bm25_score=0.55,
                vector_score=None,
                graph_score=None,
                retrieval_score=0.55,
                metadata={},
            ),
        ),
        diagnostics=RetrievalDiagnostics(
            bm25_count=2,
            vector_count=0,
            graph_added_count=0,
            precision_added_count=0,
            coverage_added_count=0,
            retrieval_disagreement=None,
            degraded=False,
            degradation_reason=None,
        ),
    )
    provider = FakeProvider(response_text="provider should not be called")
    planner = ProviderProposedPatchPlanner(
        retrieval_service=FakeRetrievalService(output=ambiguous),
        direct_read_service=DirectReadService(workspace_root=tmp_path),
        edit_proposer=ProviderBackedEditProposer(provider=provider),
    )

    result = planner.plan(request(tmp_path, target_file=None))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "target_selection_ambiguous"
    assert provider.last_request is None


def test_provider_proposed_patch_planner_rejects_provider_unknown_evidence_id(
    tmp_path: Path,
) -> None:
    planner = ProviderProposedPatchPlanner(
        retrieval_service=FakeRetrievalService(),
        direct_read_service=DirectReadService(workspace_root=tmp_path),
        edit_proposer=ProviderBackedEditProposer(
            provider=FakeProvider(
                response_text=(
                    '{"target_file":"calculator.py",'
                    '"new_content":"def add(a, b):\\n    return a + b\\n",'
                    '"rationale":"Use addition.",'
                    '"evidence_ids":["unknown"],'
                    '"risk_flags":[]}'
                )
            )
        ),
    )

    result = planner.plan(request(tmp_path))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "proposal_evidence_scope_denied"


def test_provider_proposed_patch_planner_preserves_expected_hash_gate(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use addition.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    planner = ProviderProposedPatchPlanner(
        retrieval_service=FakeRetrievalService(),
        direct_read_service=DirectReadService(workspace_root=tmp_path),
        edit_proposer=ProviderBackedEditProposer(provider=provider),
    )
    stale_request = request(tmp_path)
    stale_request = ProviderProposedPatchPlanRequest(
        task_id=stale_request.task_id,
        workspace_root=stale_request.workspace_root,
        query=stale_request.query,
        task_class=stale_request.task_class,
        index_id=stale_request.index_id,
        target_file=stale_request.target_file,
        intent=stale_request.intent,
        expected_behavior=stale_request.expected_behavior,
        verification_argv=stale_request.verification_argv,
        retrieval_policy=stale_request.retrieval_policy,
        expected_content_hash=content_hash("different\n"),
    )

    result = planner.plan(stale_request)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "stale_context"
