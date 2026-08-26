from homllm_v4.contracts.evidence import DirectReadRequest, EvidenceRetrievalRequest
from homllm_v4.contracts.tool_loop import AgentToolObservation
from homllm_v4.services.direct_read_service import DirectReadService
from homllm_v4.services.retrieval_service import EvidenceRetrievalService


class AgentToolExecutor:
    """Executes model-requested tools strictly inside the workspace boundary.

    Read access goes through :class:`DirectReadService` (path containment,
    byte cap, utf-8 enforcement); search goes through the evidence retrieval
    stack. Every observation is char-capped and this class never raises --
    failures become ``ok=False`` observations the model can react to within
    its own turn budget.
    """

    def __init__(
        self,
        *,
        retrieval_service: EvidenceRetrievalService,
        direct_read_service: DirectReadService,
        index_id: str,
        max_read_lines: int = 120,
        max_read_chars: int = 6000,
        max_search_results: int = 8,
        max_search_chars: int = 4000,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.direct_read_service = direct_read_service
        self.index_id = index_id
        self.max_read_lines = max(1, int(max_read_lines))
        self.max_read_chars = max(1, int(max_read_chars))
        self.max_search_results = max(1, int(max_search_results))
        self.max_search_chars = max(1, int(max_search_chars))

    def execute(self, *, task_id: str, name: str, arguments: object) -> AgentToolObservation:
        try:
            if not isinstance(arguments, dict):
                return _invalid_arguments(name, "arguments must be an object")
            if name == "read_file":
                return self._read_file(task_id=task_id, arguments=arguments)
            if name == "search_repo":
                return self._search_repo(task_id=task_id, arguments=arguments)
            return AgentToolObservation(ok=False, content="", error_code="unknown_tool")
        except Exception as exc:  # defensive: observations must never raise
            return AgentToolObservation(ok=False, content="", error_code=f"tool_error:{type(exc).__name__}")

    def _read_file(self, *, task_id: str, arguments: dict) -> AgentToolObservation:
        file_path = arguments.get("file_path")
        if not isinstance(file_path, str) or not file_path.strip():
            return _invalid_arguments("read_file", "file_path is required")
        start_line = _optional_line(arguments.get("start_line"))
        end_line = _optional_line(arguments.get("end_line"))
        result = self.direct_read_service.read(
            DirectReadRequest(
                task_id=task_id,
                file_path=file_path,
                require_hash=False,
            )
        )
        if not result.ok or result.output is None:
            error = result.error
            return AgentToolObservation(
                ok=False,
                content=str(getattr(error, "message", "") or ""),
                error_code=str(getattr(error, "code", "read_failed")),
            )
        window = _slice_numbered_lines(
            result.output.content_excerpt,
            start_line=start_line,
            end_line=end_line,
            max_lines=self.max_read_lines,
        )
        return _capped_observation(window, cap=self.max_read_chars)

    def _search_repo(self, *, task_id: str, arguments: dict) -> AgentToolObservation:
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            return _invalid_arguments("search_repo", "query is required")
        try:
            result = self.retrieval_service.retrieve(
                EvidenceRetrievalRequest(
                    task_id=task_id,
                    query=query,
                    task_class="agentic_search",
                    index_id=self.index_id,
                    policy={"intent": "SEARCH", "top_k": self.max_search_results},
                )
            )
        except Exception:
            return AgentToolObservation(ok=False, content="", error_code="search_failed")
        if not result.ok or result.output is None:
            error = result.error
            return AgentToolObservation(
                ok=False,
                content=str(getattr(error, "message", "") or ""),
                error_code=str(getattr(error, "code", "search_failed")),
            )
        lines = [
            _render_candidate(candidate)
            for candidate in result.output.candidates[: self.max_search_results]
        ]
        if not lines:
            lines = ["no candidates found"]
        return _capped_observation("\n".join(lines), cap=self.max_search_chars)


def _invalid_arguments(tool_name: str, reason: str) -> AgentToolObservation:
    return AgentToolObservation(
        ok=False,
        content=f"{tool_name}: {reason}",
        error_code="invalid_tool_arguments",
    )


def _optional_line(value: object) -> int | None:
    if value is None:
        return None
    try:
        return max(1, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _slice_numbered_lines(
    text: str,
    *,
    start_line: int | None,
    end_line: int | None,
    max_lines: int,
) -> str:
    lines = text.splitlines(keepends=True)
    first = 1
    last = len(lines)
    if start_line is not None or end_line is not None:
        first = max(start_line or 1, 1)
        last = min(end_line or len(lines), len(lines))
    window = lines[max(first - 1, 0) : max(last, 0)]
    if len(window) > max_lines:
        window = window[:max_lines]
        truncated_window = True
    else:
        truncated_window = False
    numbered = "".join(f"{index + first:>5}: {line}" for index, line in enumerate(window))
    if truncated_window:
        numbered += f"...[window limited to {max_lines} lines]\n"
    return numbered


def _render_candidate(candidate) -> str:
    span_start = candidate.span_start if candidate.span_start is not None else "?"
    span_end = candidate.span_end if candidate.span_end is not None else "?"
    content = str(candidate.metadata.get("content") or "")
    preview = " ".join(content.split())[:160]
    return (
        f"- {candidate.candidate_id} | {candidate.file_path}:{span_start}-{span_end}"
        f" | score={candidate.retrieval_score:.3f} | {preview}"
    )


def _capped_observation(content: str, *, cap: int) -> AgentToolObservation:
    if len(content) <= cap:
        return AgentToolObservation(ok=True, content=content)
    clipped = content[:cap]
    return AgentToolObservation(ok=True, content=f"{clipped}\n[truncated]", truncated=True)
