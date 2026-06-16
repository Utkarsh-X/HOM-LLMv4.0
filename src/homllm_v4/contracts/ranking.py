from dataclasses import dataclass

from homllm_v4.contracts.evidence import EvidenceCandidate, EvidenceSet


@dataclass(frozen=True)
class RankedEvidence:
    candidate: EvidenceCandidate
    rank: int
    final_score: float
    score_components: dict[str, float]
    reranked: bool


@dataclass(frozen=True)
class RankingDiagnostics:
    reranker_used: bool
    reranker_available: bool
    reranker_degraded_reason: str | None
    concentration_ratio: float | None
    score_separation: float | None
    top_source_channels: dict[str, int]


@dataclass(frozen=True)
class RankedEvidenceSet:
    ranked_set_id: str
    items: tuple[RankedEvidence, ...]
    diagnostics: RankingDiagnostics


@dataclass(frozen=True)
class EvidenceRankingRequest:
    task_id: str
    evidence_set: EvidenceSet
    policy: dict[str, object]
