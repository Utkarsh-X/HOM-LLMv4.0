from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DirectReadRequest:
    task_id: str
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    max_bytes: int = 20000
    require_hash: bool = True


@dataclass(frozen=True)
class DirectReadResult:
    file_path: str
    content_excerpt: str
    line_start: int | None
    line_end: int | None
    content_hash: str | None
    truncated: bool
    freshness: Literal["fresh", "possibly_stale", "stale"]


@dataclass(frozen=True)
class EvidenceCandidate:
    candidate_id: str
    file_path: str
    symbol_id: str | None
    span_start: int | None
    span_end: int | None
    content_hash: str
    source_channels: tuple[str, ...]
    bm25_score: float | None
    vector_score: float | None
    graph_score: float | None
    retrieval_score: float
    metadata: dict[str, object]


@dataclass(frozen=True)
class RetrievalDiagnostics:
    bm25_count: int
    vector_count: int
    graph_added_count: int
    precision_added_count: int
    coverage_added_count: int
    retrieval_disagreement: float | None
    degraded: bool
    degradation_reason: str | None


@dataclass(frozen=True)
class EvidenceSet:
    evidence_set_id: str
    query: str
    candidates: tuple[EvidenceCandidate, ...]
    diagnostics: RetrievalDiagnostics


@dataclass(frozen=True)
class EvidenceRetrievalRequest:
    task_id: str
    query: str
    task_class: str
    index_id: str
    policy: dict[str, object]
    target_files: tuple[str, ...] = ()
    target_symbols: tuple[str, ...] = ()
