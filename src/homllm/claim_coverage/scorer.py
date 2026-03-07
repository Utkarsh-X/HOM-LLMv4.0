"""Coverage scoring for claim packet against final context."""

from __future__ import annotations

import re

from homllm.claim_coverage.interfaces import (
    Claim,
    ClaimCoverage,
    ClaimCoverageConfig,
    ClaimPacket,
    CoverageReport,
    EvidenceAnchor,
)
from homllm.context.interfaces import ContextArtifact, ContextBlock


_WORD_RE = re.compile(r"\b[A-Za-z0-9_]+\b")


def score_claim_coverage(
    claim_packet: ClaimPacket,
    context_artifact: ContextArtifact,
    config: ClaimCoverageConfig,
) -> CoverageReport:
    """Score per-claim evidence coverage from context blocks."""
    claim_rows: list[ClaimCoverage] = []
    unresolved: list[str] = []

    for claim in claim_packet.required_claims:
        row = _score_single_claim(claim, context_artifact.blocks, config)
        claim_rows.append(row)
        if not row.covered:
            unresolved.append(claim.claim_id)

    required_count = len(claim_packet.required_claims)
    covered_count = sum(1 for r in claim_rows if r.covered)
    ratio = covered_count / required_count if required_count else 0.0
    return CoverageReport(
        required_claim_count=required_count,
        covered_required_claim_count=covered_count,
        coverage_ratio=ratio,
        unresolved_claim_ids=tuple(unresolved),
        claim_coverage=tuple(claim_rows),
    )


def _score_single_claim(
    claim: Claim,
    blocks: tuple[ContextBlock, ...],
    config: ClaimCoverageConfig,
) -> ClaimCoverage:
    best_score = 0.0
    best_lex = 0.0
    best_sym = 0.0
    best_struct = 0.0
    anchors: list[EvidenceAnchor] = []

    for block in blocks:
        lex = _lexical_anchor_match(claim, block)
        sym = _symbol_match(claim, block)
        struct = _structural_proximity(claim, block)
        score = (
            config.scoring_weights.get("lexical_anchor_match", 0.5) * lex
            + config.scoring_weights.get("symbol_match", 0.3) * sym
            + config.scoring_weights.get("structural_proximity", 0.2) * struct
        )
        if score > 0:
            anchors.append(
                EvidenceAnchor(
                    block_id=block.block_id,
                    file=block.file,
                    start_line=block.start_line,
                    end_line=block.end_line,
                    score=score,
                )
            )
        if score > best_score:
            best_score = score
            best_lex = lex
            best_sym = sym
            best_struct = struct

    anchors = sorted(anchors, key=lambda a: a.score, reverse=True)[:5]
    # Robust coverage decision:
    # 1) Weighted score gate (default behavior).
    # 2) Strong lexical evidence fallback for natural-language queries where symbol signals are sparse.
    # 3) Symbol+lexical joint gate for identifier-centric claims.
    # 4) Anchored medium-lexical fallback when multiple anchors consistently support the claim.
    threshold = float(config.claim_cover_threshold)
    strong_lexical = best_lex >= 0.75
    symbol_lexical_joint = best_sym >= 0.5 and best_lex >= 0.4
    anchored_medium_lexical = (
        len(anchors) >= 3
        and best_lex >= 0.33
        and (anchors[0].score if anchors else 0.0) >= max(0.20, threshold * 0.35)
    )
    covered = bool(anchors) and (
        best_score >= threshold
        or strong_lexical
        or symbol_lexical_joint
        or anchored_medium_lexical
    )
    return ClaimCoverage(
        claim_id=claim.claim_id,
        covered=covered,
        score=best_score,
        lexical_anchor_match=best_lex,
        symbol_match=best_sym,
        structural_proximity=best_struct,
        anchors=tuple(anchors),
    )


def _lexical_anchor_match(claim: Claim, block: ContextBlock) -> float:
    if not claim.terms:
        return 0.0
    text = (block.content or "").lower()
    hits = sum(1 for t in claim.terms if t in text)
    return min(1.0, hits / max(1, len(claim.terms)))


def _symbol_match(claim: Claim, block: ContextBlock) -> float:
    if not claim.identifier_hints:
        return 0.0
    haystack = " ".join(
        [
            (block.file or "").lower(),
            (block.symbol_id or "").lower(),
            (block.symbol_name or "").lower(),
        ]
    )
    hits = sum(1 for h in claim.identifier_hints if h.lower() in haystack)
    return min(1.0, hits / max(1, len(claim.identifier_hints)))


def _structural_proximity(claim: Claim, block: ContextBlock) -> float:
    # Simple deterministic approximation:
    # reward block if claim terms appear in file path/symbol and content together.
    file_sym = " ".join(
        [
            (block.file or "").lower(),
            (block.symbol_id or "").lower(),
            (block.symbol_name or "").lower(),
        ]
    )
    content_terms = set(_WORD_RE.findall((block.content or "").lower()))
    overlap = 0
    for t in claim.terms:
        in_structure = t in file_sym
        in_content = t in content_terms
        if in_structure and in_content:
            overlap += 1
    if not claim.terms:
        return 0.0
    return min(1.0, overlap / max(1, len(claim.terms)))
