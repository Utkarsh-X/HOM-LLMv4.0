import re
from dataclasses import dataclass
from typing import Literal

from homllm_v4.contracts.evidence import EvidenceSet

TargetSelectionDecision = Literal["selected", "ambiguous", "no_candidates"]


@dataclass(frozen=True)
class TargetFileSelectionRequest:
    task_id: str
    evidence_set: EvidenceSet


@dataclass(frozen=True)
class TargetFileSelectionResult:
    decision: TargetSelectionDecision
    target_file: str | None
    confidence: float
    reason: str | None
    candidate_file_scores: dict[str, float]


class EvidenceTargetFileSelector:
    def __init__(self, *, min_score_margin: float = 0.1, path_token_boost: float = 0.2) -> None:
        self.min_score_margin = max(0.0, float(min_score_margin))
        self.path_token_boost = max(0.0, float(path_token_boost))

    def select(self, request: TargetFileSelectionRequest) -> TargetFileSelectionResult:
        scores: dict[str, float] = {}
        for candidate in request.evidence_set.candidates:
            scores[candidate.file_path] = scores.get(candidate.file_path, 0.0) + float(
                candidate.retrieval_score or 0.0
            )

        query_tokens = _tokens(request.evidence_set.query)
        for file_path in tuple(scores):
            scores[file_path] += self.path_token_boost * len(
                query_tokens & _meaningful_path_tokens(file_path)
            )

        if not scores:
            return TargetFileSelectionResult(
                decision="no_candidates",
                target_file=None,
                confidence=0.0,
                reason="evidence_set_has_no_candidates",
                candidate_file_scores={},
            )

        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        top_file, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = top_score - second_score
        total = sum(scores.values())
        confidence = top_score / total if total > 0 else 0.0

        if len(ranked) > 1 and margin < self.min_score_margin:
            return TargetFileSelectionResult(
                decision="ambiguous",
                target_file=None,
                confidence=confidence,
                reason="top_file_scores_too_close",
                candidate_file_scores=dict(ranked),
            )

        return TargetFileSelectionResult(
            decision="selected",
            target_file=top_file,
            confidence=confidence,
            reason=None,
            candidate_file_scores=dict(ranked),
        )


def _tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^A-Za-z0-9]+", value.lower()) if token}


def _meaningful_path_tokens(file_path: str) -> set[str]:
    generic_tokens = {
        "api",
        "app",
        "core",
        "lib",
        "py",
        "src",
        "test",
        "tests",
        "utils",
    }
    return _tokens(file_path) - generic_tokens
