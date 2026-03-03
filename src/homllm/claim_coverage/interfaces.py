"""Interfaces and contracts for claim-coverage gating."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ClaimIntent(str, Enum):
    """High-level claim intent class."""

    TRACE = "TRACE"
    COMPARE = "COMPARE"
    HOW_IT_WORKS = "HOW_IT_WORKS"
    ERROR_FALLBACK = "ERROR_FALLBACK"
    ORDER_PRIORITY = "ORDER_PRIORITY"
    BEHAVIOR_EXISTS = "BEHAVIOR_EXISTS"


class GateAction(str, Enum):
    """Decision emitted by claim coverage gate."""

    PASS = "PASS"
    SOFT_RECOVERY = "SOFT_RECOVERY"
    PASS_WITH_GAPS = "PASS_WITH_GAPS"


@dataclass(frozen=True)
class Claim:
    """Atomic query claim."""

    claim_id: str
    text: str
    intent: ClaimIntent
    template: str
    terms: tuple[str, ...] = ()
    identifier_hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClaimPacket:
    """Claims extracted from query."""

    query: str
    required_claims: tuple[Claim, ...]
    optional_claims: tuple[Claim, ...] = ()
    forbidden_claims: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceAnchor:
    """Evidence location for a claim."""

    block_id: str
    file: str
    start_line: int
    end_line: int
    score: float


@dataclass(frozen=True)
class ClaimCoverage:
    """Coverage detail for one claim."""

    claim_id: str
    covered: bool
    score: float
    lexical_anchor_match: float
    symbol_match: float
    structural_proximity: float
    anchors: tuple[EvidenceAnchor, ...] = ()


@dataclass(frozen=True)
class CoverageReport:
    """Claim-coverage report."""

    required_claim_count: int
    covered_required_claim_count: int
    coverage_ratio: float
    unresolved_claim_ids: tuple[str, ...]
    claim_coverage: tuple[ClaimCoverage, ...]


@dataclass(frozen=True)
class GateDecision:
    """Gate decision with rationale."""

    action: GateAction
    reason: str
    coverage_before_recovery: float
    coverage_after_recovery: float


@dataclass
class ClaimCoverageConfig:
    """Config for claim-coverage gate."""

    enabled: bool = True
    required_coverage_threshold: float = 0.70
    claim_cover_threshold: float = 0.55
    soft_recovery_enabled: bool = True
    max_recovery_passes: int = 1
    max_required_claims: int = 8
    recovery_top_k: int = 20
    debug: bool = False
    scoring_weights: dict[str, float] = field(
        default_factory=lambda: {
            "lexical_anchor_match": 0.5,
            "symbol_match": 0.3,
            "structural_proximity": 0.2,
        }
    )
