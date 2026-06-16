import hashlib
import sys

from homllm_v4.contracts.evidence import (
    DirectReadResult,
    EvidenceCandidate,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.contracts.edit_proposal import EditProposalRequest, EditProposalResult
from homllm_v4.planning.bounded_edit_proposer import (
    BoundedEditProposer,
    evidence_plan_request_from_proposal,
)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def request() -> EditProposalRequest:
    return EditProposalRequest(
        task_id="task-1",
        target_file="calculator.py",
        intent="fix add",
        expected_behavior="add returns a sum",
        current_content="def add(a, b):\n    return a - b\n",
        evidence_ids=("cand-1",),
        allowed_file_paths=("calculator.py",),
        verification_summary="pytest . -q",
    )


def test_bounded_edit_proposer_accepts_valid_single_file_proposal() -> None:
    proposer = BoundedEditProposer(
        proposer=lambda req: EditProposalResult(
            target_file=req.target_file,
            new_content="def add(a, b):\n    return a + b\n",
            rationale="Use addition instead of subtraction.",
            evidence_ids=req.evidence_ids,
            risk_flags=(),
        )
    )

    result = proposer.propose(request())

    assert result.ok is True
    assert result.output is not None
    assert result.output.target_file == "calculator.py"
    assert "return a + b" in result.output.new_content


def test_bounded_edit_proposer_rejects_unapproved_file() -> None:
    proposer = BoundedEditProposer(
        proposer=lambda req: EditProposalResult(
            target_file="other.py",
            new_content="bad\n",
            rationale="bad",
            evidence_ids=req.evidence_ids,
            risk_flags=(),
        )
    )

    result = proposer.propose(request())

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "proposal_file_denied"


def test_bounded_edit_proposer_rejects_empty_content() -> None:
    proposer = BoundedEditProposer(
        proposer=lambda req: EditProposalResult(
            target_file=req.target_file,
            new_content="",
            rationale="empty",
            evidence_ids=req.evidence_ids,
            risk_flags=(),
        )
    )

    result = proposer.propose(request())

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "proposal_empty_content"


def test_bounded_edit_proposer_rejects_evidence_drop() -> None:
    proposer = BoundedEditProposer(
        proposer=lambda req: EditProposalResult(
            target_file=req.target_file,
            new_content=req.current_content,
            rationale="no evidence",
            evidence_ids=(),
            risk_flags=(),
        )
    )

    result = proposer.propose(request())

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "proposal_missing_evidence"


def test_evidence_plan_request_from_proposal_preserves_runtime_owned_context() -> None:
    proposal = EditProposalResult(
        target_file="calculator.py",
        new_content="def add(a, b):\n    return a + b\n",
        rationale="Use addition.",
        evidence_ids=("cand-1",),
        risk_flags=(),
    )
    direct_read = DirectReadResult(
        file_path="calculator.py",
        content_excerpt="def add(a, b):\n    return a - b\n",
        line_start=None,
        line_end=None,
        content_hash=content_hash("def add(a, b):\n    return a - b\n"),
        truncated=False,
        freshness="fresh",
    )
    evidence_set = EvidenceSet(
        evidence_set_id="evidence-1",
        query="fix add",
        candidates=(
            EvidenceCandidate(
                candidate_id="cand-1",
                file_path="calculator.py",
                symbol_id=None,
                span_start=1,
                span_end=2,
                content_hash=direct_read.content_hash,
                source_channels=("fixture",),
                bm25_score=None,
                vector_score=None,
                graph_score=None,
                retrieval_score=1.0,
                metadata={},
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

    plan_request = evidence_plan_request_from_proposal(
        task_id="task-1",
        workspace_root=".",
        intent="fix add",
        expected_behavior="add returns a sum",
        evidence_set=evidence_set,
        direct_read=direct_read,
        proposal=proposal,
        verification_argv=(sys.executable, "-m", "pytest", ".", "-q"),
    )

    assert plan_request.target_file == "calculator.py"
    assert plan_request.expected_content_hash == direct_read.content_hash
    assert plan_request.new_content == proposal.new_content
    assert plan_request.allowed_file_paths == ("calculator.py",)
