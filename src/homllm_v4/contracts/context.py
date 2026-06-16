from dataclasses import dataclass

from homllm_v4.contracts.ranking import RankedEvidenceSet


@dataclass(frozen=True)
class ContextBlock:
    block_id: str
    candidate_id: str
    file_path: str
    span_start: int | None
    span_end: int | None
    text: str
    token_count: int
    score: float
    citation: str


@dataclass(frozen=True)
class ContextPack:
    context_pack_id: str
    purpose: str
    text: str
    blocks: tuple[ContextBlock, ...]
    used_tokens: int
    dropped_candidates: tuple[str, ...]
    diagnostics: dict[str, object]


@dataclass(frozen=True)
class ContextPackRequest:
    task_id: str
    ranked_evidence_set: RankedEvidenceSet
    policy: dict[str, object]
    query: str = ""
