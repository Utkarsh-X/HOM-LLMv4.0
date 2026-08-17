import hashlib
import sys
from dataclasses import replace

from homllm_v4.contracts.evidence import (
    DirectReadResult,
    EvidenceCandidate,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.planning.evidence_patch_planner import (
    EvidenceBackedPatchPlanRequest,
    EvidenceBackedPatchPlanner,
)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def evidence_set(file_path: str = "calculator.py") -> EvidenceSet:
    return EvidenceSet(
        evidence_set_id="evidence-1",
        query="fix add",
        candidates=(
            EvidenceCandidate(
                candidate_id="cand-1",
                file_path=file_path,
                symbol_id=None,
                span_start=1,
                span_end=2,
                content_hash=content_hash("def add(a, b):\n    return a - b\n"),
                source_channels=("bm25",),
                bm25_score=1.0,
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


def direct_read(file_path: str, content: str, freshness: str = "fresh") -> DirectReadResult:
    return DirectReadResult(
        file_path=file_path,
        content_excerpt=content,
        line_start=None,
        line_end=None,
        content_hash=content_hash(content),
        truncated=False,
        freshness=freshness,
    )


def request(
    *,
    evidence: EvidenceSet | None = None,
    read: DirectReadResult | None = None,
    expected_hash: str | None = None,
    allowed_file_paths: tuple[str, ...] | None = None,
) -> EvidenceBackedPatchPlanRequest:
    original = "def add(a, b):\n    return a - b\n"
    fixed = "def add(a, b):\n    return a + b\n"
    return EvidenceBackedPatchPlanRequest(
        task_id="task-1",
        workspace_root=".",
        target_file="calculator.py",
        intent="fix add",
        expected_behavior="add returns a sum",
        evidence_set=evidence or evidence_set(),
        direct_reads=(read or direct_read("calculator.py", original),),
        expected_content_hash=expected_hash or content_hash(original),
        new_content=fixed,
        verification_argv=(sys.executable, "-m", "pytest", ".", "-q"),
        allowed_file_paths=allowed_file_paths,
    )


def test_evidence_patch_planner_creates_patch_request_from_fresh_evidence() -> None:
    result = EvidenceBackedPatchPlanner().plan(request())

    assert result.ok is True
    assert result.output is not None
    assert result.output.patch_plan.target_files == ("calculator.py",)
    assert result.output.patch_plan.evidence_ids == ("cand-1",)
    assert result.output.patch_request.allowed_file_paths == ("calculator.py",)
    assert result.output.patch_request.patches[0].expected_content_hash == content_hash(
        "def add(a, b):\n    return a - b\n"
    )
    assert result.output.verification_commands[0].argv == (sys.executable, "-m", "pytest", ".", "-q")


def test_evidence_patch_planner_uses_default_verification_timeout() -> None:
    result = EvidenceBackedPatchPlanner().plan(request())
    assert result.output is not None
    assert result.output.verification_commands[0].timeout_seconds == 60


def test_evidence_patch_planner_honors_configured_verification_timeout() -> None:
    result = EvidenceBackedPatchPlanner().plan(
        replace(request(), verification_timeout_seconds=120)
    )
    assert result.output is not None
    assert result.output.verification_commands[0].timeout_seconds == 120


def test_evidence_patch_planner_rejects_zero_verification_timeout() -> None:
    result = EvidenceBackedPatchPlanner().plan(
        replace(request(), verification_timeout_seconds=0)
    )
    assert result.output is not None
    assert result.output.verification_commands[0].timeout_seconds == 1


def test_evidence_patch_planner_rejects_missing_target_evidence() -> None:
    result = EvidenceBackedPatchPlanner().plan(request(evidence=evidence_set("other.py")))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "missing_target_evidence"


def test_evidence_patch_planner_rejects_stale_direct_read() -> None:
    stale = direct_read("calculator.py", "def add(a, b):\n    return a - b\n", freshness="stale")

    result = EvidenceBackedPatchPlanner().plan(request(read=stale))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "stale_direct_read"


def test_evidence_patch_planner_rejects_hash_mismatch() -> None:
    result = EvidenceBackedPatchPlanner().plan(request(expected_hash=content_hash("different\n")))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "stale_context"


def test_evidence_patch_planner_preserves_allowed_file_scope() -> None:
    result = EvidenceBackedPatchPlanner().plan(
        request(allowed_file_paths=("approved.py",))
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.patch_request.allowed_file_paths == ("approved.py",)
