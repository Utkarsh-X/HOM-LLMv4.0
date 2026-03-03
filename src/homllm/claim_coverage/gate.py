"""Claim-coverage gate orchestration."""

from __future__ import annotations

from dataclasses import asdict

from homllm.claim_coverage.extractor import extract_claim_packet
from homllm.claim_coverage.interfaces import (
    ClaimCoverageConfig,
    ClaimPacket,
    CoverageReport,
    GateAction,
    GateDecision,
)
from homllm.claim_coverage.scorer import score_claim_coverage
from homllm.context.interfaces import ContextArtifact


def run_claim_coverage(
    query: str,
    context_artifact: ContextArtifact,
    config: ClaimCoverageConfig,
) -> tuple[ClaimPacket, CoverageReport]:
    """Build claim packet and score coverage against context."""
    packet = extract_claim_packet(
        query=query,
        max_required_claims=config.max_required_claims,
    )
    report = score_claim_coverage(packet, context_artifact, config)
    return packet, report


def decide_gate_action(
    report: CoverageReport,
    config: ClaimCoverageConfig,
    *,
    recovery_attempted: bool,
    coverage_before_recovery: float | None = None,
) -> GateDecision:
    """Determine gate action from report and policy config."""
    before = (
        float(coverage_before_recovery)
        if coverage_before_recovery is not None
        else float(report.coverage_ratio)
    )
    after = float(report.coverage_ratio)
    threshold = float(config.required_coverage_threshold)
    if report.coverage_ratio >= threshold:
        return GateDecision(
            action=GateAction.PASS,
            reason=f"coverage_ratio={report.coverage_ratio:.3f} >= {threshold:.3f}",
            coverage_before_recovery=before,
            coverage_after_recovery=after,
        )
    if config.soft_recovery_enabled and not recovery_attempted:
        return GateDecision(
            action=GateAction.SOFT_RECOVERY,
            reason=f"coverage_ratio={report.coverage_ratio:.3f} < {threshold:.3f}",
            coverage_before_recovery=before,
            coverage_after_recovery=after,
        )
    return GateDecision(
        action=GateAction.PASS_WITH_GAPS,
        reason=f"coverage_ratio={report.coverage_ratio:.3f} < {threshold:.3f} after recovery",
        coverage_before_recovery=before,
        coverage_after_recovery=after,
    )


def build_unresolved_claim_queries(
    packet: ClaimPacket,
    report: CoverageReport,
    max_queries: int = 4,
) -> list[str]:
    """Build focused retrieval queries for unresolved claims."""
    claim_map = {c.claim_id: c for c in packet.required_claims}
    out: list[str] = []
    for claim_id in report.unresolved_claim_ids:
        claim = claim_map.get(claim_id)
        if not claim:
            continue
        hints = " ".join(claim.identifier_hints[:4]).strip()
        terms = " ".join(claim.terms[:8]).strip()
        parts = [claim.text.strip()]
        if hints:
            parts.append(hints)
        if terms:
            parts.append(terms)
        out.append(" | ".join(parts))
        if len(out) >= max(1, int(max_queries)):
            break
    return out


def packet_to_prompt_text(packet: ClaimPacket) -> str:
    """Render claims checklist for prompt variables."""
    lines = []
    for claim in packet.required_claims:
        lines.append(f"- [{claim.claim_id}] {claim.text}")
    return "\n".join(lines) if lines else "- (no required claims extracted)"


def evidence_map_to_prompt_text(packet: ClaimPacket, report: CoverageReport) -> str:
    """Render evidence map for prompt variables."""
    by_id = {r.claim_id: r for r in report.claim_coverage}
    lines: list[str] = []
    for claim in packet.required_claims:
        row = by_id.get(claim.claim_id)
        if row is None:
            lines.append(f"- [{claim.claim_id}] UNRESOLVED: no scoring row")
            continue
        status = "SUPPORTED" if row.covered else "UNRESOLVED"
        if row.anchors:
            anchor = row.anchors[0]
            lines.append(
                f"- [{claim.claim_id}] {status}: {anchor.file}:{anchor.start_line}-{anchor.end_line} "
                f"(score={row.score:.2f})"
            )
        else:
            lines.append(f"- [{claim.claim_id}] {status}: no evidence anchor")
    return "\n".join(lines)


def coverage_summary_to_prompt_text(report: CoverageReport) -> str:
    """Render coverage summary for prompt variables."""
    unresolved = ", ".join(report.unresolved_claim_ids) if report.unresolved_claim_ids else "none"
    return (
        f"required_claim_count={report.required_claim_count}; "
        f"covered_required_claim_count={report.covered_required_claim_count}; "
        f"coverage_ratio={report.coverage_ratio:.3f}; "
        f"unresolved={unresolved}"
    )


def to_serializable_dict(obj) -> dict:
    """Dataclass to dict helper for artifact writes."""
    return asdict(obj)
