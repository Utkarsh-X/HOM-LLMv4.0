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
    limit = max(1, int(max_queries))
    claim_map = {c.claim_id: c for c in packet.required_claims}
    out: list[str] = []
    seen: set[str] = set()

    def _add(query_text: str) -> None:
        q = " ".join((query_text or "").split()).strip()
        if not q:
            return
        k = q.lower()
        if k in seen:
            return
        seen.add(k)
        out.append(q)

    unresolved_claims = [
        claim_map[cid] for cid in report.unresolved_claim_ids if cid in claim_map
    ]
    if unresolved_claims:
        # Prefer non-error intents first so recovery doesn't get dominated by error/fallback claims.
        try:
            from homllm.claim_coverage.interfaces import ClaimIntent
        except Exception:
            ClaimIntent = None  # type: ignore[assignment]
        if ClaimIntent:
            intent_priority = {
                ClaimIntent.TRACE: 0,
                ClaimIntent.HOW_IT_WORKS: 1,
                ClaimIntent.BEHAVIOR_EXISTS: 1,
                ClaimIntent.ORDER_PRIORITY: 2,
                ClaimIntent.COMPARE: 2,
                ClaimIntent.ERROR_FALLBACK: 3,
            }
            unresolved_claims.sort(
                key=lambda c: (intent_priority.get(c.intent, 2), c.claim_id)
            )
    if unresolved_claims:
        # Global unresolved focus keeps broad context that per-claim segmentation can lose.
        unresolved_text = " ; ".join(c.text.strip() for c in unresolved_claims if c.text.strip())
        _add(f"{packet.query.strip()} | unresolved focus: {unresolved_text}")

    # First pass: ensure each unresolved claim gets one recovery query.
    for claim in unresolved_claims:
        hints = " ".join(claim.identifier_hints[:4]).strip()
        terms = " ".join(claim.terms[:8]).strip()
        parts = [claim.text.strip()]
        if hints:
            parts.append(hints)
        if terms:
            parts.append(terms)
        _add(" | ".join(parts))
        if len(out) >= limit:
            return out[:limit]

    # Second pass: add intent-aware auxiliary queries only if room remains.
    for claim in unresolved_claims:
        if len(out) >= limit:
            break
        intent_terms = _intent_expansion_terms(claim)
        if intent_terms:
            hints = " ".join(claim.identifier_hints[:4]).strip()
            aux_parts = [claim.text.strip(), " ".join(intent_terms)]
            if hints:
                aux_parts.append(hints)
            _add(" | ".join(p for p in aux_parts if p))
    return out[:limit]


def _intent_expansion_terms(claim) -> tuple[str, ...]:
    """Deterministic intent-aware expansion terms (query-agnostic)."""
    from homllm.claim_coverage.interfaces import ClaimIntent

    mapping = {
        ClaimIntent.TRACE: ("execution", "flow", "sequence", "step"),
        ClaimIntent.COMPARE: ("difference", "tradeoff", "comparison", "when"),
        ClaimIntent.HOW_IT_WORKS: ("implementation", "logic", "behavior", "path"),
        ClaimIntent.ERROR_FALLBACK: ("error", "fallback", "retry", "failure"),
        ClaimIntent.ORDER_PRIORITY: ("priority", "order", "precedence", "before", "after"),
        ClaimIntent.BEHAVIOR_EXISTS: ("implementation", "code", "behavior"),
    }
    base = list(mapping.get(claim.intent, ()))
    # Add top claim terms (already normalized) to retain local semantics.
    for t in claim.terms[:6]:
        if t not in base:
            base.append(t)
    dedup: list[str] = []
    seen: set[str] = set()
    for t in base:
        k = str(t).strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        dedup.append(str(t).strip())
    return tuple(dedup[:12])


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
