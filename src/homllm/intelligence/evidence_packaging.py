"""Evidence packaging helpers for generation-time answer planning."""

from __future__ import annotations

from dataclasses import dataclass
import re

from homllm.claim_coverage.interfaces import ClaimIntent
from homllm.intelligence.answer_contracts import classify_query_shape


@dataclass(frozen=True)
class EvidencePacketBundle:
    """Structured evidence summaries derived from the final context only."""

    prompt_header: str = ""
    packet_types: tuple[str, ...] = ()

    @property
    def active(self) -> bool:
        return bool(self.prompt_header.strip())


_STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "when",
    "how",
    "does",
    "what",
    "where",
    "which",
    "into",
    "across",
    "between",
    "using",
    "about",
    "system",
    "handle",
    "handles",
    "all",
    "complex",
    "compare",
    "each",
    "through",
    "including",
    "describe",
    "trace",
    "flow",
    "sequence",
    "behavior",
    "work",
    "works",
    "interact",
    "interaction",
}

_ENTRY_MARKERS = (
    "entry",
    "handle",
    "handler",
    "request",
    "decorator",
    "middleware",
    "wrapper",
    "extract",
    "receive",
    "header",
)
_PROCESSING_MARKERS = (
    "validate",
    "decode",
    "transform",
    "process",
    "execute",
    "apply",
    "parse",
    "check",
    "verify",
)
_DOWNSTREAM_MARKERS = (
    "return",
    "result",
    "payload",
    "store",
    "submit",
    "forward",
    "consumer",
    "downstream",
)
_FAILURE_MARKERS = (
    "raise",
    "except",
    "error",
    "invalid",
    "expired",
    "failed",
    "failure",
)


def _query_terms(query: str) -> tuple[str, ...]:
    terms: list[str] = []
    seen: set[str] = set()
    for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]+", (query or "").lower()):
        if len(tok) < 4 or tok in _STOP_WORDS or tok in seen:
            continue
        seen.add(tok)
        terms.append(tok)
    return tuple(terms)


def _claim_intents(claim_packet) -> set[ClaimIntent]:
    if claim_packet is None:
        return set()
    return {claim.intent for claim in getattr(claim_packet, "required_claims", ()) or ()}


def _query_identifier_hints(query: str, claim_packet=None) -> tuple[str, ...]:
    hints: list[str] = []
    seen: set[str] = set()
    if claim_packet is not None:
        for claim in getattr(claim_packet, "required_claims", ()) or ():
            for hint in getattr(claim, "identifier_hints", ()) or ():
                key = str(hint).strip().lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                hints.append(str(hint).strip())
    if hints:
        return tuple(hints)

    for match in re.findall(r"\b[A-Z][A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)?\b|\b[a-z]+_[a-z0-9_]+\b", query or ""):
        key = match.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        hints.append(match.strip())
    return tuple(hints)


def _extract_comparison_items(query: str) -> tuple[str, ...]:
    q = " ".join((query or "").split()).strip()
    if not q:
        return ()
    match = re.search(r"\bcompare\b\s+(.+?)(?:[?.]|$)", q, flags=re.IGNORECASE)
    segment = match.group(1) if match else q
    segment = re.sub(r"\bwhen to use each\b.*$", "", segment, flags=re.IGNORECASE).strip(" -,:;")
    raw_parts = re.split(r"\s*(?:,|\band\b|\bor\b|\bvs\b|\bversus\b)\s*", segment, flags=re.IGNORECASE)
    items: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        cleaned = " ".join(part.split()).strip(" -,:;")
        if len(cleaned) < 3:
            continue
        lowered = cleaned.lower()
        if lowered in _STOP_WORDS or lowered in seen:
            continue
        seen.add(lowered)
        items.append(cleaned)
    return tuple(items[:6])


def _item_terms(item: str) -> tuple[str, ...]:
    return tuple(tok for tok in _query_terms(item) if tok not in {"strategy", "format", "mode"})


def _block_text(block) -> str:
    return " ".join(
        [
            str(getattr(block, "file", "") or ""),
            str(getattr(block, "symbol_name", "") or ""),
            str(getattr(block, "symbol_id", "") or ""),
            str(getattr(block, "content", "") or "")[:1400],
        ]
    ).lower()


def _block_ref(block) -> str:
    file_name = str(getattr(block, "file", "") or "").strip() or "unknown_file"
    symbol = str(getattr(block, "symbol_name", "") or "").strip()
    if symbol:
        return f"{file_name}:{symbol}"
    return file_name


def _count_hits(text: str, markers: tuple[str, ...]) -> int:
    return sum(1 for marker in markers if marker in text)


def _best_role_block(
    blocks,
    role_markers: tuple[str, ...],
    query_terms: tuple[str, ...],
    identifier_hints: tuple[str, ...],
    excluded_block_ids: set[int] | None = None,
):
    best_block = None
    best_score = 0
    excluded_block_ids = excluded_block_ids or set()
    for block in blocks:
        if id(block) in excluded_block_ids:
            continue
        hay = _block_text(block)
        score = _count_hits(hay, role_markers)
        score += sum(1 for term in query_terms if term in hay)
        score += 2 * sum(1 for hint in identifier_hints if hint.lower() in hay)
        if score > best_score:
            best_score = score
            best_block = block
    return best_block if best_score > 0 else None


def _build_flow_chain_packet(query: str, context_artifact, claim_packet=None) -> str:
    blocks = tuple(getattr(context_artifact, "blocks", ()) or ())
    query_terms = _query_terms(query)
    identifier_hints = _query_identifier_hints(query, claim_packet=claim_packet)
    used: set[int] = set()

    entry_block = _best_role_block(blocks, _ENTRY_MARKERS, query_terms, identifier_hints)
    if entry_block is not None:
        used.add(id(entry_block))

    processing_block = _best_role_block(
        blocks, _PROCESSING_MARKERS, query_terms, identifier_hints, excluded_block_ids=used
    )
    if processing_block is not None:
        used.add(id(processing_block))

    downstream_block = _best_role_block(
        blocks, _DOWNSTREAM_MARKERS, query_terms, identifier_hints, excluded_block_ids=used
    )
    if downstream_block is not None:
        used.add(id(downstream_block))

    failure_block = _best_role_block(
        blocks, _FAILURE_MARKERS, query_terms, identifier_hints, excluded_block_ids=used
    )

    lines = [
        "Flow chain packet (derived only from the retrieved context):",
        f"- Entry boundary: {_block_ref(entry_block) if entry_block else 'not directly shown in final context'}",
        f"- First processing step: {_block_ref(processing_block) if processing_block else 'not directly shown in final context'}",
        f"- Downstream consumer/use: {_block_ref(downstream_block) if downstream_block else 'not directly shown in final context'}",
        f"- Failure handling: {_block_ref(failure_block) if failure_block else 'not directly shown in final context'}",
        "- Use this packet to organize the answer in order; do not treat it as extra evidence beyond the cited blocks.",
    ]
    return "\n".join(lines)


def _matching_blocks(blocks, item_terms: tuple[str, ...]):
    if not item_terms:
        return ()
    scored = []
    for block in blocks:
        hay = _block_text(block)
        hits = sum(1 for term in item_terms if term in hay)
        if hits <= 0:
            continue
        scored.append((hits, block))
    scored.sort(key=lambda row: (-row[0], _block_ref(row[1])))
    return tuple(block for _, block in scored)


def _build_comparison_matrix_packet(query: str, context_artifact) -> str:
    blocks = tuple(getattr(context_artifact, "blocks", ()) or ())
    items = _extract_comparison_items(query)
    if not items:
        return ""

    lines = [
        "Comparison matrix packet (derived only from the retrieved context):",
        "- For each named alternative, distinguish direct evidence from absence of direct evidence.",
    ]
    for item in items:
        item_terms = _item_terms(item)
        matches = _matching_blocks(blocks, item_terms)
        if matches:
            refs = ", ".join(_block_ref(block) for block in matches[:2])
            status = "direct evidence present in final context"
        else:
            refs = "no directly matching block in final context"
            status = "no direct evidence present in final context"
        lines.append(f"- {item}: {status}; supporting refs: {refs}")
    lines.append(
        "- Use this packet to keep coverage balanced across the named alternatives before adding adjacent details."
    )
    return "\n".join(lines)


def build_evidence_packets(query: str, context_artifact, claim_packet=None) -> EvidencePacketBundle:
    """Build generic evidence packets from the final context artifact."""

    query_class = classify_query_shape(query, claim_packet=claim_packet)
    packet_texts: list[str] = []
    packet_types: list[str] = []
    claim_intents = _claim_intents(claim_packet)

    if query_class == "flow" or ClaimIntent.TRACE in claim_intents:
        flow_packet = _build_flow_chain_packet(query, context_artifact, claim_packet=claim_packet)
        if flow_packet:
            packet_types.append("flow_chain")
            packet_texts.append(flow_packet)

    if query_class == "comparison" or ClaimIntent.COMPARE in claim_intents:
        comparison_packet = _build_comparison_matrix_packet(query, context_artifact)
        if comparison_packet:
            packet_types.append("comparison_matrix")
            packet_texts.append(comparison_packet)

    if not packet_texts:
        return EvidencePacketBundle()

    header = (
        "Pre-Structured Evidence Packets:\n"
        "These packets are summaries derived from the same retrieved context. Use them to organize the answer, "
        "not as extra evidence beyond the cited blocks.\n\n"
        + "\n\n".join(packet_texts)
    )
    return EvidencePacketBundle(
        prompt_header=header,
        packet_types=tuple(packet_types),
    )
