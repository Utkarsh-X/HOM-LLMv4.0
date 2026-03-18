"""Ranked-surface evidence planner for generation-time answer organization."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable

from homllm.claim_coverage.interfaces import ClaimIntent
from homllm.intelligence.answer_contracts import classify_query_shape


@dataclass(frozen=True)
class EvidenceSupportRef:
    file: str
    symbol_name: str | None
    doc_id: str
    snippet: str
    role: str
    source_surface: str  # "final_context" | "ranked_surface"


@dataclass(frozen=True)
class EvidencePacket:
    packet_type: str
    summary: str
    support_refs: tuple[EvidenceSupportRef, ...]


@dataclass(frozen=True)
class EvidencePlan:
    query_class: str
    packet_types: tuple[str, ...] = ()
    prompt_header: str = ""
    packets: tuple[EvidencePacket, ...] = ()
    omitted_helper_refs: int = 0
    support_surface_size: int = 0
    packet_ref_count: int = 0

    @property
    def active(self) -> bool:
        return bool(self.prompt_header.strip())


@dataclass(frozen=True)
class _SupportItem:
    doc_id: str
    file: str
    symbol_name: str | None
    content: str
    source_surface: str
    rank_index: int
    from_final_context: bool


_STOP_WORDS = {
    "the", "and", "for", "with", "from", "that", "this", "when", "how", "does", "what",
    "where", "which", "into", "across", "between", "using", "about", "system", "handle",
    "handles", "all", "complex", "compare", "each", "through", "including", "describe",
    "trace", "flow", "sequence", "behavior", "work", "works", "interact", "interaction",
}

_ENTRY_MARKERS = ("decorator", "wrapper", "middleware", "request", "header", "extract", "entry", "start")
_PROCESSING_MARKERS = ("validate", "decode", "transform", "process", "execute", "check", "verify")
_DOWNSTREAM_MARKERS = ("return", "payload", "use", "consumer", "subject", "result", "admin")
_FAILURE_MARKERS = ("raise", "except", "error", "invalid", "expired", "failed", "missing")

_INTERACTION_MARKERS = {
    "entry_or_planning": ("plan", "planning", "entry", "query", "build"),
    "rule_application": ("optimize", "rewrite", "rule", "apply", "pushdown", "fold"),
    "cost_or_selection": ("cost", "select", "estimate", "choose", "best"),
    "cache_or_short_circuit": ("cache", "cached", "hit", "miss", "short-circuit"),
    "execution_and_timing": ("execute", "execution", "timing", "timer", "metrics", "latency"),
}

_TANGENT_MARKERS = ("retry", "fallback", "parsing", "parser", "indexer", "async job")
_HELPER_MARKERS = ("estimate", "helper", "utility", "validate_only", "mock", "__init__.py")
_HELPER_EXCEPTION_MARKERS = ("internal", "helper", "heuristic", "estimate", "calculation", "exact logic")
_ENTRY_REQUIRED_MARKERS = ("extract", "header", "request", "decorator", "wrapper", "middleware")
_SYSTEM_SCOPE_NOISE_MARKERS = ("validate_file_path", "ttl", "cache key", "file path")
_INTERACTION_SYMBOL_PENALTIES = ("get_stats", "optimizationrule")


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


def _query_requests_explicit_extraction(query: str) -> bool:
    q = (query or "").lower()
    return any(marker in q for marker in ("extract", "extraction", "header", "request"))


def _query_requests_numeric_mechanism(query: str) -> bool:
    q = (query or "").lower()
    markers = (
        "formula",
        "score",
        "scores",
        "similarity",
        "cosine",
        "nan",
        "percentile",
        "percentiles",
        "p50",
        "p95",
        "p99",
        "dimension",
        "mismatch",
        "weights",
    )
    return any(marker in q for marker in markers)


def _query_mentions_named_rules(query: str) -> bool:
    q = query or ""
    return bool(
        re.search(r"\b[A-Z][A-Z0-9_]{2,}\b", q)
        or re.search(r"\b[a-z]+_[a-z0-9_]+\b", q)
    )


def _query_named_symbols(query: str) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for match in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]+\b", query or ""):
        if not re.search(r"[A-Z_]", match):
            continue
        key = match.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(match)
    return tuple(out)


def _derive_primary_subject_hints(query: str, claim_packet=None) -> tuple[str, ...]:
    if (query or "").lower().strip().startswith("compare "):
        return ()
    hints = _query_identifier_hints(query, claim_packet=claim_packet)
    subject_hints: list[str] = []
    for hint in hints:
        cleaned = hint.strip()
        if not cleaned:
            continue
        if cleaned.lower() in {"json", "pickle"}:
            continue
        subject_hints.append(cleaned)
    return tuple(subject_hints[:3])


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
    return tuple(tok for tok in _query_terms(item) if tok not in {"strategy", "policy", "format", "mode"})


def _normalize_snippet(text: str, limit: int = 180) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _support_item_key(doc_id: str, file: str, symbol_name: str | None) -> str:
    return f"{doc_id}|{file}|{symbol_name or ''}"


def _build_support_surface(ranking_output, context_artifact, ranked_limit: int = 40) -> list[_SupportItem]:
    surface: list[_SupportItem] = []
    seen: set[str] = set()

    for block in tuple(getattr(context_artifact, "blocks", ()) or ()):
        file_value = str(getattr(block, "file", "") or "")
        if not file_value:
            continue
        item = _SupportItem(
            doc_id=str(getattr(block, "block_id", "") or ""),
            file=file_value,
            symbol_name=getattr(block, "symbol_name", None),
            content=str(getattr(block, "content", "") or ""),
            source_surface="final_context",
            rank_index=-1,
            from_final_context=True,
        )
        key = _support_item_key(item.doc_id, item.file, item.symbol_name)
        if key in seen:
            continue
        seen.add(key)
        surface.append(item)

    for idx, cand in enumerate(tuple(getattr(ranking_output, "ranked_candidates", ()) or ())[:ranked_limit], start=1):
        file_value = str(getattr(cand, "file", "") or "")
        if not file_value:
            continue
        item = _SupportItem(
            doc_id=str(getattr(cand, "doc_id", "") or ""),
            file=file_value,
            symbol_name=getattr(cand, "symbol_name", None),
            content=str(getattr(cand, "content", "") or ""),
            source_surface="ranked_surface",
            rank_index=idx,
            from_final_context=False,
        )
        key = _support_item_key(item.doc_id, item.file, item.symbol_name)
        if key in seen:
            continue
        seen.add(key)
        surface.append(item)
    return surface


def _query_requests_helper_detail(query: str) -> bool:
    q = (query or "").lower()
    return any(marker in q for marker in _HELPER_EXCEPTION_MARKERS)


def _is_helper_like(item: _SupportItem) -> bool:
    symbol_name = (item.symbol_name or "").strip()
    file_name = (item.file or "").lower()
    hay = f"{symbol_name} {item.content[:500]}".lower()
    if symbol_name.startswith("_"):
        return True
    if any(marker in hay or marker in file_name for marker in _HELPER_MARKERS):
        return True
    return False


def _role_hits(item: _SupportItem, markers: Iterable[str]) -> int:
    hay = f"{item.file} {item.symbol_name or ''} {item.content[:1200]}".lower()
    return sum(1 for marker in markers if marker in hay)


def _term_hits(item: _SupportItem, terms: Iterable[str]) -> int:
    hay = f"{item.file} {item.symbol_name or ''} {item.content[:1200]}".lower()
    return sum(1 for term in terms if term in hay)


def _score_item(
    item: _SupportItem,
    query_terms: tuple[str, ...],
    identifier_hints: tuple[str, ...],
    role_markers: Iterable[str] = (),
    helper_exception: bool = False,
) -> int:
    score = 0
    if item.from_final_context:
        score += 30
    else:
        score += max(0, 12 - item.rank_index)

    if not _is_helper_like(item):
        score += 12
    elif not helper_exception:
        score -= 10

    if item.symbol_name and not str(item.symbol_name).startswith("_"):
        score += 5

    score += 5 * _role_hits(item, role_markers)
    score += min(8, _term_hits(item, query_terms))
    score += 4 * _term_hits(item, [hint.lower() for hint in identifier_hints])
    return score


def _same_subsystem(a: _SupportItem | None, b: _SupportItem | None) -> bool:
    if a is None or b is None:
        return False
    a_parts = [part for part in (a.file or "").split("/") if part]
    b_parts = [part for part in (b.file or "").split("/") if part]
    if not a_parts or not b_parts:
        return False
    return a_parts[0] == b_parts[0]


def _extract_symbol_calls(item: _SupportItem | None) -> tuple[str, ...]:
    if item is None:
        return ()
    seen: set[str] = set()
    calls: list[str] = []
    for match in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", item.content or ""):
        key = match.lower()
        if key in seen:
            continue
        seen.add(key)
        calls.append(match)
    return tuple(calls)


def _make_ref(item: _SupportItem, role: str) -> EvidenceSupportRef:
    return EvidenceSupportRef(
        file=item.file or "unknown_file",
        symbol_name=item.symbol_name,
        doc_id=item.doc_id,
        snippet=_normalize_snippet(item.content),
        role=role,
        source_surface=item.source_surface,
    )


def _pick_best(
    support_surface: list[_SupportItem],
    query_terms: tuple[str, ...],
    identifier_hints: tuple[str, ...],
    role_markers: Iterable[str],
    used_doc_ids: set[str],
    helper_exception: bool,
    *,
    require_role_hit: bool = False,
    allow_helper_fallback: bool = False,
) -> _SupportItem | None:
    best: _SupportItem | None = None
    best_score = 0
    helper_best: _SupportItem | None = None
    helper_best_score = 0
    for item in support_surface:
        if item.doc_id in used_doc_ids:
            continue
        role_hits = _role_hits(item, role_markers)
        if require_role_hit and role_hits <= 0:
            continue
        score = _score_item(item, query_terms, identifier_hints, role_markers, helper_exception=helper_exception)
        if _is_helper_like(item) and not helper_exception:
            if score > helper_best_score:
                helper_best_score = score
                helper_best = item
            continue
        if score > best_score:
            best_score = score
            best = item
    if best_score > 0:
        return best
    if allow_helper_fallback and helper_best_score > 0:
        return helper_best
    return None


def _build_flow_chain_packet(
    query: str,
    support_surface: list[_SupportItem],
    claim_packet=None,
) -> EvidencePacket | None:
    query_terms = _query_terms(query)
    identifier_hints = _query_identifier_hints(query, claim_packet=claim_packet)
    named_symbols = _query_named_symbols(query)
    helper_exception = _query_requests_helper_detail(query)
    requires_explicit_extraction = _query_requests_explicit_extraction(query)
    used_doc_ids: set[str] = set()
    support_refs: list[EvidenceSupportRef] = []

    role_map = {
        "entry_boundary": _ENTRY_MARKERS,
        "primary_processing": _PROCESSING_MARKERS,
        "downstream_use": _DOWNSTREAM_MARKERS,
        "failure_handling": _FAILURE_MARKERS,
    }

    lines = ["Flow chain packet:"]
    for role, markers in role_map.items():
        role_identifier_hints = identifier_hints
        if role == "entry_boundary" and requires_explicit_extraction and not identifier_hints:
            role_identifier_hints = _ENTRY_REQUIRED_MARKERS
        item = _pick_best(
            support_surface,
            query_terms,
            role_identifier_hints,
            markers,
            used_doc_ids,
            helper_exception,
            require_role_hit=True,
            allow_helper_fallback=False,
        )
        if (
            role == "entry_boundary"
            and requires_explicit_extraction
            and item is not None
            and _role_hits(item, _ENTRY_REQUIRED_MARKERS) <= 0
            and not any(
                (item.symbol_name or "").lower() == hint.lower()
                for hint in named_symbols
            )
        ):
            item = None
        if item is None:
            lines.append(f"- {role}: entry boundary not directly shown in retrieved support surface" if role == "entry_boundary" else f"- {role}: not directly shown in retrieved support surface")
            continue
        used_doc_ids.add(item.doc_id)
        support_refs.append(_make_ref(item, role))
        ref_text = f"{item.file}:{item.symbol_name}" if item.symbol_name else item.file
        lines.append(f"- {role}: {ref_text} ({item.source_surface})")
        if role == "entry_boundary":
            entry_calls = _extract_symbol_calls(item)
            if entry_calls:
                identifier_hints = tuple(dict.fromkeys(identifier_hints + entry_calls))

    lines.append("- Use this as answer ordering support only; do not invent missing steps.")
    return EvidencePacket("flow_chain", "\n".join(lines), tuple(support_refs))


def _build_comparison_matrix_packet(query: str, support_surface: list[_SupportItem], claim_packet=None) -> EvidencePacket | None:
    items = _extract_comparison_items(query)
    if not items:
        return None
    primary_subject_hints = _derive_primary_subject_hints(query, claim_packet=claim_packet)
    support_refs: list[EvidenceSupportRef] = []
    lines = [
        "Comparison matrix packet:",
        "- Cover each named alternative evenly before adding adjacent details.",
        "- If an item has no direct evidence in the primary component support surface, state that and do not import other subsystems to fill the gap.",
    ]
    for item_name in items:
        item_terms = _item_terms(item_name)
        def _comparison_score(item: _SupportItem) -> int:
            score = _score_item(item, item_terms, (), (), helper_exception=True)
            if primary_subject_hints:
                score += 6 * _term_hits(item, [hint.lower() for hint in primary_subject_hints])
            return score

        matches = sorted(support_surface, key=_comparison_score, reverse=True)
        matches = [item for item in matches if _term_hits(item, item_terms) > 0][:2]
        if primary_subject_hints:
            primary_matches = [
                item
                for item in matches
                if _term_hits(item, [hint.lower() for hint in primary_subject_hints]) > 0
            ]
            matches = primary_matches
        if matches:
            refs = ", ".join(
                f"{item.file}:{item.symbol_name}" if item.symbol_name else item.file
                for item in matches
            )
            lines.append(f"- {item_name}: direct evidence present; refs: {refs}")
            for match in matches:
                support_refs.append(_make_ref(match, f"comparison:{item_name}"))
        else:
            if primary_subject_hints:
                lines.append(f"- {item_name}: no direct evidence present in primary component support surface")
            else:
                lines.append(f"- {item_name}: no direct evidence present in support surface")
    return EvidencePacket("comparison_matrix", "\n".join(lines), tuple(support_refs))


def _build_system_scope_packet(query: str, support_surface: list[_SupportItem]) -> EvidencePacket | None:
    query_terms = _query_terms(query)
    helper_exception = _query_requests_helper_detail(query)
    ranked = sorted(
        support_surface,
        key=lambda item: _score_item(item, query_terms, (), (), helper_exception=helper_exception),
        reverse=True,
    )
    aligned: list[_SupportItem] = []
    tangents: list[str] = []
    seen_files: set[str] = set()
    fallback_candidates: list[_SupportItem] = []
    for item in ranked:
        hay = f"{item.file} {item.symbol_name or ''} {item.content[:1200]}".lower()
        direct_overlap = _term_hits(item, query_terms)
        tangent = any(marker in hay for marker in _TANGENT_MARKERS) and direct_overlap == 0
        if tangent:
            tangents.append(f"{item.file}:{item.symbol_name}" if item.symbol_name else item.file)
            continue
        if any(marker in hay for marker in _SYSTEM_SCOPE_NOISE_MARKERS):
            continue
        min_overlap = 2 if len(query_terms) >= 4 else 1
        if direct_overlap < min_overlap:
            if direct_overlap > 0:
                fallback_candidates.append(item)
            continue
        aligned.append(item)
        seen_files.add(item.file)
        if len(aligned) >= 4 and len(seen_files) >= 2:
            break
    if not aligned:
        for item in fallback_candidates:
            aligned.append(item)
            seen_files.add(item.file)
            if len(aligned) >= 4 and len(seen_files) >= 2:
                break
    if not aligned:
        return None
    support_refs = tuple(_make_ref(item, "system_scope") for item in aligned)
    lines = [
        "System scope map:",
        "- primary_components: " + ", ".join(
            f"{item.file}:{item.symbol_name}" if item.symbol_name else item.file for item in aligned
        ),
        "- runtime_behavior: stay within these aligned components before adding broad advice.",
        "- failure_or_gap_points: mention only gaps evidenced by these components.",
        "- excluded_tangents: " + (", ".join(tangents[:3]) if tangents else "none"),
    ]
    return EvidencePacket("system_scope_map", "\n".join(lines), support_refs)


def _build_interaction_packet(query: str, support_surface: list[_SupportItem], claim_packet=None) -> EvidencePacket | None:
    query_terms = _query_terms(query)
    identifier_hints = _query_identifier_hints(query, claim_packet=claim_packet)
    helper_exception = _query_requests_helper_detail(query)
    used_doc_ids: set[str] = set()
    support_refs: list[EvidenceSupportRef] = []
    lines = ["Interaction path packet:"]
    last_selected: _SupportItem | None = None

    for role, markers in _INTERACTION_MARKERS.items():
        best_item = None
        best_score = None
        for candidate in support_surface:
            if candidate.doc_id in used_doc_ids:
                continue
            if _role_hits(candidate, markers) <= 0:
                continue
            if role in {"rule_application", "cost_or_selection"} and _is_helper_like(candidate) and not helper_exception:
                continue
            score = _score_item(
                candidate,
                query_terms,
                identifier_hints,
                markers,
                helper_exception=helper_exception,
            )
            if last_selected is not None and _same_subsystem(last_selected, candidate):
                score += 8
            if _is_helper_like(candidate) and not helper_exception:
                score -= 18
            if (candidate.symbol_name or "").lower() in _INTERACTION_SYMBOL_PENALTIES:
                score -= 20
            if role == "cost_or_selection" and _role_hits(candidate, ("cost", "estimate", "select", "choose")) <= 0:
                score -= 12
            if role == "execution_and_timing" and _role_hits(candidate, ("execute", "execution", "timing", "timer", "metrics", "latency", "duration")) <= 0:
                score -= 12
            if best_score is None or score > best_score:
                best_score = score
                best_item = candidate
        item = best_item if (best_score is not None and best_score > 0) else None
        if item is None:
            lines.append(f"- {role}: not directly shown in retrieved support surface")
            continue
        used_doc_ids.add(item.doc_id)
        support_refs.append(_make_ref(item, role))
        ref_text = f"{item.file}:{item.symbol_name}" if item.symbol_name else item.file
        lines.append(f"- {role}: {ref_text} ({item.source_surface})")
        last_selected = item

    lines.append("- Build exactly one compact path from these roles; do not fill gaps with helper speculation.")
    return EvidencePacket("interaction_path", "\n".join(lines), tuple(support_refs))


def build_evidence_plan(query: str, ranking_output, context_artifact, claim_packet=None) -> EvidencePlan:
    query_class = classify_query_shape(query, claim_packet=claim_packet)
    claim_intents = _claim_intents(claim_packet)
    support_surface = _build_support_surface(ranking_output, context_artifact, ranked_limit=40)
    helper_exception = _query_requests_helper_detail(query)
    skip_interaction_packet = _query_requests_numeric_mechanism(query) or _query_mentions_named_rules(query)

    packets: list[EvidencePacket] = []
    if query_class == "flow" or ClaimIntent.TRACE in claim_intents:
        packet = _build_flow_chain_packet(query, support_surface, claim_packet=claim_packet)
        if packet:
            packets.append(packet)
    if query_class == "comparison" or ClaimIntent.COMPARE in claim_intents:
        packet = _build_comparison_matrix_packet(query, support_surface, claim_packet=claim_packet)
        if packet:
            packets.append(packet)
    if query_class == "system_scope":
        packet = _build_system_scope_packet(query, support_surface)
        if packet:
            packets.append(packet)
    if (query_class == "interaction" or ClaimIntent.ORDER_PRIORITY in claim_intents) and not skip_interaction_packet:
        packet = _build_interaction_packet(query, support_surface, claim_packet=claim_packet)
        if packet:
            packets.append(packet)

    if not packets:
        return EvidencePlan(query_class=query_class, support_surface_size=len(support_surface))

    used_doc_ids = {ref.doc_id for packet in packets for ref in packet.support_refs}
    omitted_helper_refs = sum(
        1
        for item in support_surface
        if _is_helper_like(item) and item.doc_id not in used_doc_ids and not helper_exception
    )
    packet_ref_count = sum(len(packet.support_refs) for packet in packets)
    packet_text = "\n\n".join(packet.summary for packet in packets)
    header = (
        "Evidence plan (derived only from retrieved evidence):\n"
        "- This plan is an organizational aid, not permission to invent facts.\n"
        "- Missing roles/items remain missing if the retrieved support surface does not show them.\n\n"
        f"{packet_text}"
    )
    return EvidencePlan(
        query_class=query_class,
        packet_types=tuple(packet.packet_type for packet in packets),
        prompt_header=header,
        packets=tuple(packets),
        omitted_helper_refs=omitted_helper_refs,
        support_surface_size=len(support_surface),
        packet_ref_count=packet_ref_count,
    )
