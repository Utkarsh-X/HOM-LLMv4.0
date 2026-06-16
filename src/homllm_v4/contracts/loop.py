from dataclasses import dataclass
from typing import Literal

from homllm_v4.contracts.context import ContextPack
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import EvidenceSet
from homllm_v4.contracts.ranking import RankedEvidenceSet

StopReason = Literal[
    "sufficient",
    "empty_evidence",
    "repeated_state",
    "budget_exhausted",
    "service_failed",
]


@dataclass(frozen=True)
class ReadOnlyLoopRequest:
    task_id: str
    run_id: str
    workspace_root: str
    query: str
    max_passes: int = 3
    min_candidates: int = 2
    min_context_blocks: int = 2
    index_artifact_paths: dict[str, str] | None = None


@dataclass(frozen=True)
class SufficiencyDecision:
    sufficient: bool
    score: float
    missing_reasons: tuple[str, ...]
    evidence_candidate_count: int
    context_block_count: int


@dataclass(frozen=True)
class ClaimSupport:
    claim_id: str
    claim_text: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class LoopPassRecord:
    pass_index: int
    evidence_set: EvidenceSet
    ranked_evidence_set: RankedEvidenceSet
    context_pack: ContextPack
    sufficiency: SufficiencyDecision


@dataclass(frozen=True)
class ReadOnlyLoopResult:
    task_id: str
    run_id: str
    stop_reason: StopReason
    pass_count: int
    sufficiency: SufficiencyDecision
    passes: tuple[LoopPassRecord, ...]
    context_pack: ContextPack | None
    response_text: str
    claim_support: tuple[ClaimSupport, ...]
    error: CapabilityError | None = None
