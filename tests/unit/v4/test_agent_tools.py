from dataclasses import dataclass, field
from pathlib import Path

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import (
    DirectReadRequest,
    DirectReadResult,
    EvidenceCandidate,
    EvidenceRetrievalRequest,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.runtime.agent_tools import AgentToolExecutor


def direct_result(excerpt: str) -> DirectReadResult:
    return DirectReadResult(
        file_path="src/a.py",
        content_excerpt=excerpt,
        line_start=None,
        line_end=None,
        content_hash="hash",
        truncated=False,
        freshness="fresh",
    )


def ok_read(excerpt: str) -> CapabilityResult[DirectReadResult]:
    return CapabilityResult(
        capability_name="file.read",
        ok=True,
        output=direct_result(excerpt),
        error=None,
        telemetry=None,
        artifacts=(),
    )


def failed_read(code: str) -> CapabilityResult[DirectReadResult]:
    return CapabilityResult(
        capability_name="file.read",
        ok=False,
        output=None,
        error=CapabilityError(code=code, message="boom", recoverable=True, retryable=False),
        telemetry=None,
        artifacts=(),
    )


def evidence_set() -> EvidenceSet:
    candidate = EvidenceCandidate(
        candidate_id="cand-1",
        file_path="src/a.py",
        symbol_id=None,
        span_start=10,
        span_end=25,
        content_hash="h",
        source_channels=("bm25",),
        bm25_score=2.5,
        vector_score=None,
        graph_score=None,
        retrieval_score=0.87,
        metadata={"content": "def run():\n    return 1"},
    )
    return EvidenceSet(
        evidence_set_id="set-1",
        query="run",
        candidates=(candidate,),
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


@dataclass
class StubReadService:
    result: CapabilityResult[DirectReadResult]
    requests: list[DirectReadRequest] = field(default_factory=list)

    def read(self, request: DirectReadRequest) -> CapabilityResult[DirectReadResult]:
        self.requests.append(request)
        return self.result


@dataclass
class StubRetrievalService:
    result: CapabilityResult[EvidenceSet] | None = None
    raise_error: Exception | None = None
    requests: list[EvidenceRetrievalRequest] = field(default_factory=list)

    def retrieve(self, request: EvidenceRetrievalRequest) -> CapabilityResult[EvidenceSet]:
        if self.raise_error is not None:
            raise self.raise_error
        self.requests.append(request)
        assert self.result is not None
        return self.result


def executor(read_service: StubReadService, retrieval_service: StubRetrievalService) -> AgentToolExecutor:
    return AgentToolExecutor(
        retrieval_service=retrieval_service,
        direct_read_service=read_service,
        index_id="idx-1",
    )


def test_read_file_renders_numbered_lines(tmp_path: Path) -> None:
    reader = StubReadService(result=ok_read("alpha\nbeta\ngamma\n"))
    tool = executor(reader, StubRetrievalService())

    observation = tool.execute(
        task_id="task-1",
        name="read_file",
        arguments={"file_path": "src/a.py", "start_line": 2, "end_line": 3},
    )

    assert observation.ok is True
    assert observation.content == "    2: beta\n    3: gamma\n"
    assert observation.truncated is False
    request = reader.requests[0]
    assert request.file_path == "src/a.py"
    assert request.require_hash is False


def test_read_file_marks_truncation(tmp_path: Path) -> None:
    reader = StubReadService(result=ok_read("line-one\nline-two\n"))
    tool = AgentToolExecutor(
        retrieval_service=StubRetrievalService(),
        direct_read_service=reader,
        index_id="idx-1",
        max_read_chars=12,
    )

    observation = tool.execute(task_id="task-1", name="read_file", arguments={"file_path": "a.txt"})

    assert observation.ok is True
    assert observation.truncated is True
    assert "[truncated]" in observation.content


def test_read_file_failure_translates_to_error_observation() -> None:
    tool = executor(StubReadService(result=failed_read("file_not_found")), StubRetrievalService())

    observation = tool.execute(task_id="task-1", name="read_file", arguments={"file_path": "nope.py"})

    assert observation.ok is False
    assert observation.error_code == "file_not_found"


def test_search_repo_renders_candidates() -> None:
    retriever = StubRetrievalService(
        result=CapabilityResult(
            capability_name="evidence.retrieve",
            ok=True,
            output=evidence_set(),
            error=None,
            telemetry=None,
            artifacts=(),
        )
    )
    tool = executor(StubReadService(result=ok_read("x")), retriever)

    observation = tool.execute(task_id="task-1", name="search_repo", arguments={"query": "run"})

    assert observation.ok is True
    assert "cand-1 | src/a.py:10-25 | score=0.870 | def run(): return 1" in observation.content
    request = retriever.requests[0]
    assert request.index_id == "idx-1"
    assert request.task_class == "agentic_search"
    assert request.policy == {"intent": "SEARCH", "top_k": 8}


def test_search_repo_handles_service_errors() -> None:
    retriever = StubRetrievalService(
        result=CapabilityResult(
            capability_name="evidence.retrieve",
            ok=False,
            output=None,
            error=CapabilityError(code="adapter_failed", message="boom", recoverable=True, retryable=False),
            telemetry=None,
            artifacts=(),
        )
    )
    tool = executor(StubReadService(result=ok_read("x")), retriever)

    observation = tool.execute(task_id="task-1", name="search_repo", arguments={"query": "q"})

    assert observation.ok is False
    assert observation.error_code == "adapter_failed"


def test_search_repo_survives_unexpected_exceptions() -> None:
    retriever = StubRetrievalService(raise_error=RuntimeError("crash"))
    tool = executor(StubReadService(result=ok_read("x")), retriever)

    observation = tool.execute(task_id="task-1", name="search_repo", arguments={"query": "q"})

    assert observation.ok is False
    assert observation.error_code == "search_failed"


def test_unknown_tool_and_invalid_arguments() -> None:
    tool = executor(StubReadService(result=ok_read("x")), StubRetrievalService())

    unknown = tool.execute(task_id="task-1", name="write_file", arguments={})
    assert unknown.ok is False
    assert unknown.error_code == "unknown_tool"

    missing_query = tool.execute(task_id="task-1", name="search_repo", arguments={"query": "  "})
    assert missing_query.error_code == "invalid_tool_arguments"

    missing_path = tool.execute(task_id="task-1", name="read_file", arguments={})
    assert missing_path.error_code == "invalid_tool_arguments"

    not_dict = tool.execute(task_id="task-1", name="read_file", arguments="a.py")
    assert not_dict.error_code == "invalid_tool_arguments"
