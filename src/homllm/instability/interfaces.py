"""
Cross-Run Instability Detection — Output contract and input types (Problem 3).

Read-only diagnostic layer. No mutation of retrieval, ranking, generation, or prompts.
Exactly one primary label; strongest instability signal wins; conservative bias.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

# --- Primary label (exactly one; spec § Output Contract) ---
PrimaryLabelType = Literal["STABLE", "UNSTABLE_CONTEXT", "UNSTABLE_REASONING"]

# --- P1 verdict for failure frequency (raw only; anti-amplification) ---
VerdictType = Literal["SUFFICIENT", "PROBABLY_SUFFICIENT", "INSUFFICIENT"]


@dataclass(frozen=True)
class RunRecord:
    """
    Single historical run for instability analysis (spec § Inputs).

    Caller provides: query, intent, retrieval metadata, context summary, answer, verdict.
    policy_influenced: if True, this run is excluded from raw failure counts (anti-amplification).
    query_embedding / context_centroid_embedding: optional, for bucketing and embedding consistency.
    """

    query: str
    intent: str  # ARCHITECTURAL | IMPLEMENTATION | BEHAVIORAL | UNKNOWN
    chunk_ids: tuple[str, ...]
    file_paths: tuple[str, ...]  # for metadata variance (file-type distribution)
    answer_text: str
    final_verdict: VerdictType  # P1 sufficiency verdict
    policy_influenced: bool = False
    query_embedding: tuple[float, ...] | None = None
    context_centroid_embedding: tuple[float, ...] | None = None


@dataclass(frozen=True)
class SignalScore:
    """Per-signal score and label for auditability (spec § Auditability)."""

    signal_name: str
    score: float  # instability score in [0, 1]; higher = more unstable
    label: PrimaryLabelType | None  # CONTEXT | REASONING | None (STABLE)
    threshold_triggered: bool = False


@dataclass(frozen=True)
class InstabilityResult:
    """
    Output contract (spec § Output Contract, § Auditability).

    Exactly one primary_label. confidence = correctness likelihood; evidence_volume reported separately.
    primary_deciding_signal and secondary_contributors for blame attribution.
    """

    primary_label: PrimaryLabelType
    confidence: float
    evidence_volume: int
    explanation: dict[str, float]  # per-signal scores for audit
    primary_deciding_signal: str
    secondary_contributors: tuple[str, ...] = ()
    cold_start: bool = False
    per_signal_scores: tuple[SignalScore, ...] = ()
    thresholds_triggered: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        """Machine-readable for logging and blame attribution."""
        return {
            "primary_label": self.primary_label,
            "confidence": self.confidence,
            "evidence_volume": self.evidence_volume,
            "explanation": self.explanation,
            "primary_deciding_signal": self.primary_deciding_signal,
            "secondary_contributors": list(self.secondary_contributors),
            "cold_start": self.cold_start,
            "per_signal_scores": [
                {
                    "signal_name": s.signal_name,
                    "score": round(s.score, 4),
                    "label": s.label,
                    "threshold_triggered": s.threshold_triggered,
                }
                for s in self.per_signal_scores
            ],
            "thresholds_triggered": list(self.thresholds_triggered),
        }


class EmbedderLike(Protocol):
    """Minimal protocol for query embedding (bucketing) and optional centroid."""

    def embed_query(self, query: str) -> "VectorLike": ...
    @property
    def dimension(self) -> int: ...


class VectorLike(Protocol):
    """Minimal vector for cosine similarity (frozen embeddings)."""

    values: tuple[float, ...]


__all__ = [
    "EmbedderLike",
    "InstabilityResult",
    "PrimaryLabelType",
    "RunRecord",
    "SignalScore",
    "VerdictType",
    "VectorLike",
]
