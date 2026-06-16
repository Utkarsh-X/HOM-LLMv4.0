import hashlib
import sys
from pathlib import Path

from homllm_v4.adapters.v3_retrieval_adapter import V3RetrievalAdapter
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import DirectReadRequest, DirectReadResult
from homllm_v4.planning.retrieval_patch_planner import (
    RetrievalBackedPatchPlanRequest,
    RetrievalBackedPatchPlanner,
)
from homllm_v4.services.direct_read_service import DirectReadService
from homllm_v4.services.retrieval_service import EvidenceRetrievalService


def content_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


class FakeCandidate:
    doc_id = "doc-1"
    file = "calculator.py"
    symbol_id = None
    content = "def add(a, b):\n    return a - b\n"
    bm25_score = 1.0
    vector_score = None
    hybrid_score = 1.0
    provenance = ("bm25",)
    span_start = 1
    span_end = 2


class FakeRetrievalResult:
    query_id = "query-1"
    metadata = {"bm25_count": 1, "vector_count": 0}

    def __init__(self, file_path: str = "calculator.py") -> None:
        candidate = FakeCandidate()
        candidate.file = file_path
        self.candidates = [candidate]


class FakeRetrievalPipeline:
    def __init__(self, file_path: str = "calculator.py") -> None:
        self.file_path = file_path

    def retrieve(self, query, intent, top_k):
        return FakeRetrievalResult(self.file_path)


class FailingDirectReadService:
    def read(self, request: DirectReadRequest):
        return CapabilityResult(
            capability_name="file.read",
            ok=False,
            output=None,
            error=CapabilityError(
                code="file_not_found",
                message="missing",
                recoverable=True,
                retryable=False,
                details={"file_path": request.file_path},
            ),
            telemetry=None,
            artifacts=(),
        )


def request(tmp_path: Path) -> RetrievalBackedPatchPlanRequest:
    original = "def add(a, b):\n    return a - b\n"
    fixed = "def add(a, b):\n    return a + b\n"
    (tmp_path / "calculator.py").write_text(original, encoding="utf-8")
    return RetrievalBackedPatchPlanRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        query="fix add",
        task_class="python_patch",
        index_id="idx",
        target_file="calculator.py",
        intent="fix add",
        expected_behavior="add returns sum",
        new_content=fixed,
        verification_argv=(sys.executable, "-m", "pytest", ".", "-q"),
        retrieval_policy={"intent": "EXPLAIN", "top_k": 5},
        expected_content_hash=content_hash(original),
    )


def test_retrieval_backed_patch_planner_uses_retrieval_and_direct_read(tmp_path: Path) -> None:
    planner = RetrievalBackedPatchPlanner(
        retrieval_service=EvidenceRetrievalService(
            adapter=V3RetrievalAdapter(pipeline=FakeRetrievalPipeline())
        ),
        direct_read_service=DirectReadService(workspace_root=tmp_path),
    )

    result = planner.plan(request(tmp_path))

    assert result.ok is True
    assert result.output is not None
    assert result.output.patch_plan.target_files == ("calculator.py",)
    assert result.output.patch_plan.evidence_ids == ("doc-1",)
    assert result.output.patch_request.patches[0].file_path == "calculator.py"


def test_retrieval_backed_patch_planner_rejects_missing_target_evidence(tmp_path: Path) -> None:
    planner = RetrievalBackedPatchPlanner(
        retrieval_service=EvidenceRetrievalService(
            adapter=V3RetrievalAdapter(pipeline=FakeRetrievalPipeline("other.py"))
        ),
        direct_read_service=DirectReadService(workspace_root=tmp_path),
    )

    result = planner.plan(request(tmp_path))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "missing_target_evidence"


def test_retrieval_backed_patch_planner_returns_direct_read_error(tmp_path: Path) -> None:
    planner = RetrievalBackedPatchPlanner(
        retrieval_service=EvidenceRetrievalService(
            adapter=V3RetrievalAdapter(pipeline=FakeRetrievalPipeline())
        ),
        direct_read_service=FailingDirectReadService(),
    )

    result = planner.plan(request(tmp_path))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "file_not_found"
