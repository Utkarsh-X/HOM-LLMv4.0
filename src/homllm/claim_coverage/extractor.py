"""Deterministic claim extraction from user query."""

from __future__ import annotations

import re

from homllm.claim_coverage.interfaces import Claim, ClaimIntent, ClaimPacket

_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with",
    "how", "what", "when", "where", "which", "does", "do", "is", "are",
    "all", "through", "between", "across", "from", "that", "this",
}
_NON_IDENTIFIER_HINTS = {
    "how",
    "what",
    "when",
    "where",
    "why",
    "which",
    "who",
}

_SPLIT_RE = re.compile(r"\s*(?:,|;|\band\b|\bor\b)\s*", flags=re.IGNORECASE)
_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_]+\b")
_ID_HINT_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)?\b|\b[A-Z][A-Z0-9_]{2,}\b|\b[a-z]+_[a-z0-9_]+\b|\b[A-Za-z0-9_]+\.py\b"
)


def _detect_intent(query_lc: str, segment_lc: str) -> ClaimIntent:
    if any(t in query_lc for t in ("trace", "flow", "sequence", "pipeline", "end-to-end")):
        return ClaimIntent.TRACE
    if any(t in query_lc for t in ("compare", "contrast", "vs", "difference")):
        return ClaimIntent.COMPARE
    if any(t in query_lc for t in ("priority", "order", "resolve conflict", "precedence")):
        return ClaimIntent.ORDER_PRIORITY
    if any(t in query_lc for t in ("error", "fallback", "retry", "fail", "miss")):
        return ClaimIntent.ERROR_FALLBACK
    if segment_lc.startswith("how ") or " how " in query_lc:
        return ClaimIntent.HOW_IT_WORKS
    return ClaimIntent.BEHAVIOR_EXISTS


def _extract_terms(text: str) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for tok in _TOKEN_RE.findall(text):
        t = tok.lower()
        if len(t) < 2 or t in _STOPWORDS:
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return tuple(out)


def _extract_identifier_hints(text: str) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _ID_HINT_RE.findall(text):
        h = m.strip()
        if not h:
            continue
        if h.lower() in _NON_IDENTIFIER_HINTS:
            continue
        k = h.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(h)
    return tuple(out)


def extract_claim_packet(query: str, max_required_claims: int = 8) -> ClaimPacket:
    """Extract deterministic claim packet from query text."""
    q = (query or "").strip()
    q_lc = q.lower()
    raw_segments = [s.strip() for s in _SPLIT_RE.split(q) if s.strip()]
    if not raw_segments:
        raw_segments = [q]

    claims: list[Claim] = []
    for idx, segment in enumerate(raw_segments[: max(1, int(max_required_claims))], start=1):
        segment_lc = segment.lower()
        intent = _detect_intent(q_lc, segment_lc)
        terms = _extract_terms(segment)
        id_hints = _extract_identifier_hints(segment)
        claims.append(
            Claim(
                claim_id=f"C{idx}",
                text=segment,
                intent=intent,
                template=_template_for_intent(intent),
                terms=terms,
                identifier_hints=id_hints,
            )
        )

    forbidden = (
        "invented_identifiers",
        "unsupported_control_flow",
        "unbacked_api_claims",
    )
    return ClaimPacket(
        query=q,
        required_claims=tuple(claims),
        optional_claims=(),
        forbidden_claims=forbidden,
    )


def _template_for_intent(intent: ClaimIntent) -> str:
    if intent == ClaimIntent.TRACE:
        return "order_or_sequence"
    if intent == ClaimIntent.COMPARE:
        return "interaction_between_components"
    if intent == ClaimIntent.ERROR_FALLBACK:
        return "fallback_or_error_path"
    if intent == ClaimIntent.ORDER_PRIORITY:
        return "order_or_sequence"
    return "behavior_exists"
