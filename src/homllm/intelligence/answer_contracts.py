"""Generic answer-shape contracts driven by intent and evidence, not repo nouns."""

from __future__ import annotations

from dataclasses import dataclass
import re

from homllm.claim_coverage.interfaces import ClaimIntent


@dataclass(frozen=True)
class AnswerShapeContract:
    """Extra answer constraints layered on top of generic reasoning contracts."""

    enforcement_prompt: str = ""
    structure_prompt: str = ""
    completion_prompt: str = ""
    query_class: str = "default"
    absent_code_mode: bool = False

    @property
    def active(self) -> bool:
        return bool(self.enforcement_prompt or self.structure_prompt or self.completion_prompt)


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
}


def _query_terms(query: str) -> set[str]:
    terms: set[str] = set()
    for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]+", (query or "").lower()):
        if len(tok) < 4 or tok in _STOP_WORDS:
            continue
        terms.add(tok)
    return terms


def _block_has_direct_overlap(block, query_terms: set[str]) -> bool:
    if not query_terms:
        return False
    file_hay = str(getattr(block, "file", "") or "").lower()
    symbol_hay = " ".join(
        [
            str(getattr(block, "symbol_name", "") or ""),
            str(getattr(block, "symbol_id", "") or ""),
        ]
    ).lower()
    content_hay = str(getattr(block, "content", "") or "")[:600].lower()

    symbol_hits = sum(1 for term in query_terms if term in symbol_hay)
    if symbol_hits >= 1:
        return True

    total_hits = sum(1 for term in query_terms if term in file_hay or term in content_hay)
    return total_hits >= 2


def _block_has_identifier_overlap(block, identifier_hints: tuple[str, ...]) -> bool:
    if not identifier_hints:
        return False
    file_hay = str(getattr(block, "file", "") or "").lower()
    symbol_hay = " ".join(
        [
            str(getattr(block, "symbol_name", "") or ""),
            str(getattr(block, "symbol_id", "") or ""),
        ]
    ).lower()
    content_hay = str(getattr(block, "content", "") or "")[:600].lower()
    for hint in identifier_hints:
        needle = str(hint).strip().lower()
        if not needle:
            continue
        if needle in symbol_hay or needle in file_hay or needle in content_hay:
            return True
    return False


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


def _unique_file_count(context_artifact) -> int:
    files = {
        str(getattr(block, "file", "") or "").strip()
        for block in tuple(getattr(context_artifact, "blocks", ()) or ())
    }
    files.discard("")
    return len(files)


def _has_upstream_entry_evidence(context_artifact) -> bool:
    blocks = tuple(getattr(context_artifact, "blocks", ()) or ())
    patterns = (
        "decorator",
        "wrapper",
        "middleware",
        "request.",
        "header",
        "extract",
        "receive",
        "entry",
    )
    for block in blocks:
        hay = " ".join(
            [
                str(getattr(block, "file", "") or ""),
                str(getattr(block, "symbol_name", "") or ""),
                str(getattr(block, "symbol_id", "") or ""),
                str(getattr(block, "content", "") or "")[:1200],
            ]
        ).lower()
        if any(pat in hay for pat in patterns):
            return True
    return False


def _query_requests_entry(query: str) -> bool:
    q = (query or "").lower()
    return any(
        marker in q
        for marker in ("including extraction", "entry", "extraction", "where it enters", "start")
    )


def _extract_comparison_items(query: str) -> tuple[str, ...]:
    q = " ".join((query or "").split()).strip()
    if not q:
        return ()
    m = re.search(r"\bcompare\b\s+(.+?)(?:[?.]|$)", q, flags=re.IGNORECASE)
    segment = m.group(1) if m else q
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


def _query_focus_terms(query: str, limit: int = 8) -> tuple[str, ...]:
    terms = sorted(_query_terms(query))
    return tuple(terms[:limit])


def _context_mentions_any(context_artifact, markers: tuple[str, ...]) -> bool:
    blocks = tuple(getattr(context_artifact, "blocks", ()) or ())
    if not blocks:
        return False
    for block in blocks:
        hay = " ".join(
            [
                str(getattr(block, "file", "") or ""),
                str(getattr(block, "symbol_name", "") or ""),
                str(getattr(block, "symbol_id", "") or ""),
                str(getattr(block, "content", "") or "")[:1600],
            ]
        ).lower()
        if any(marker in hay for marker in markers):
            return True
    return False


def _query_requests_configuration(query: str) -> bool:
    q = (query or "").lower()
    return any(marker in q for marker in ("config", "configuration", "secret", "algorithm", "setting", "env"))


def _query_requests_examples(query: str) -> bool:
    q = (query or "").lower()
    return any(marker in q for marker in ("example", "for instance", "e.g.", "when to use"))


def _query_mentions_named_rules(query: str) -> bool:
    q = query or ""
    return bool(
        re.search(r"\b[A-Z][A-Z0-9_]{2,}\b", q)
        or re.search(r"\b[a-z]+_[a-z0-9_]+\b", q)
    )


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


def _query_requests_interface_exactness(query: str) -> bool:
    q = (query or "").lower()
    exactness_markers = (
        "serialize",
        "deserial",
        "json",
        "pickle",
        "storage",
        "serializer",
        "retries",
        "retry",
    )
    hit_count = sum(1 for marker in exactness_markers if marker in q)
    return hit_count >= 2


def classify_query_shape(query: str, claim_packet=None) -> str:
    q = (query or "").strip().lower()
    if not q:
        return "default"

    intents = _claim_intents(claim_packet)
    if ClaimIntent.COMPARE in intents or any(t in q for t in ("compare", "contrast", " vs ", " versus ")):
        return "comparison"
    if ClaimIntent.TRACE in intents or any(
        t in q for t in ("trace", "flow", "sequence", "pipeline", "through all layers", "end-to-end")
    ):
        return "flow"
    if any(t in q for t in ("across the system", "across components", "across layers", "across adapters", "across the stack")):
        return "system_scope"
    if "system" in q and any(t in q for t in ("fallback", "fallbacks", "checks", "missing", "handle")):
        return "system_scope"
    if ClaimIntent.ORDER_PRIORITY in intents or any(
        t in q for t in ("combine", "interact", "interaction", "priority", "order", "precedence", "resolve conflict")
    ):
        return "interaction"
    return "default"


def should_use_absent_code_mode(query: str, context_artifact, coverage_report, claim_packet=None) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return False

    intents = _claim_intents(claim_packet)
    mechanistic = bool(
        intents.intersection(
            {
                ClaimIntent.TRACE,
                ClaimIntent.HOW_IT_WORKS,
                ClaimIntent.ERROR_FALLBACK,
                ClaimIntent.ORDER_PRIORITY,
            }
        )
    ) or any(q.startswith(prefix) for prefix in ("how does", "how do", "how should", "what happens", "trace", "describe"))
    if not mechanistic:
        return False

    unresolved_ids = tuple(getattr(coverage_report, "unresolved_claim_ids", ()) or ())
    if not unresolved_ids:
        return False
    coverage_ratio = float(getattr(coverage_report, "coverage_ratio", 1.0) or 0.0)
    if coverage_ratio >= 0.55:
        return False

    blocks = tuple(getattr(context_artifact, "blocks", ()) or ())
    identifier_hints = _query_identifier_hints(query, claim_packet=claim_packet)
    if identifier_hints and not any(_block_has_identifier_overlap(block, identifier_hints) for block in blocks):
        return True

    if "fallback chain" in q and not _context_mentions_any(context_artifact, ("fallback", "fallbacks")):
        return True

    if q.startswith("how should"):
        return True

    query_terms = _query_terms(query)
    if any(_block_has_direct_overlap(block, query_terms) for block in blocks):
        return False

    return True


def build_answer_shape_contract(
    query: str,
    context_artifact,
    coverage_report,
    claim_packet=None,
) -> AnswerShapeContract:
    query_class = classify_query_shape(query, claim_packet=claim_packet)
    absent_code_mode = should_use_absent_code_mode(
        query,
        context_artifact,
        coverage_report,
        claim_packet=claim_packet,
    )
    has_entry_evidence = _has_upstream_entry_evidence(context_artifact)
    wants_entry = _query_requests_entry(query)
    unique_files = _unique_file_count(context_artifact)
    query_identifiers = _query_identifier_hints(query, claim_packet=claim_packet)
    comparison_items = _extract_comparison_items(query)
    focus_terms = _query_focus_terms(query)
    has_cache_evidence = _context_mentions_any(context_artifact, ("cache", "cached", "plan_cache"))
    has_timing_evidence = _context_mentions_any(context_artifact, ("timing", "duration", "execution_time", "duration_ms", "metric", "stats"))
    has_cost_evidence = _context_mentions_any(context_artifact, ("cost", "estimate", "estimated"))
    query_requests_configuration = _query_requests_configuration(query)
    query_requests_examples = _query_requests_examples(query)
    query_mentions_named_rules = _query_mentions_named_rules(query)
    query_requests_numeric_mechanism = _query_requests_numeric_mechanism(query)
    query_requests_interface_exactness = _query_requests_interface_exactness(query)

    enforcement_parts: list[str] = [
        "EVIDENCE ANCHOR RULE:\n"
        "- Mention file names, symbols, decorators, enums, states, helper names, and module names only when they are directly shown in the provided context.\n"
        "- If a code-specific name is not directly shown, describe the behavior generically instead of naming it.\n"
        "- Do not infer sibling decorators, neighboring modules, or adjacent implementation details from naming patterns alone.\n"
        "- Do not add file/symbol references or line-specific claims unless they are directly supported by the provided context.\n"
    ]
    structure_sections: list[str] = []

    if absent_code_mode:
        enforcement_parts.append(
            "ABSENT-CODE RESPONSE MODE:\n"
            "- If the provided repo context does not show the requested mechanism directly, do not stop at abstention.\n"
            "- Use a labeled 'Repo Finding' section stating what the repo does and does not show.\n"
            "- Then use a labeled 'General Guidance' section with bounded best-practice guidance that is clearly non-repo-grounded.\n"
            "- Add an optional 'Design Note' only if it helps explain how to make the mechanism easier to inspect in the future.\n"
            "- Never present general guidance as repo behavior.\n"
            "- Never invent file, symbol, or control-flow evidence for the missing mechanism.\n"
        )
        structure_sections.extend(["## Repo Finding", "## General Guidance", "## Design Note"])

    if query_class == "flow":
        enforcement_parts.append(
            "FLOW CONTRACT:\n"
            "- Cover the end-to-end flow in order: entry, validation or transformation, downstream use, and failure paths.\n"
            "- Prefer concrete handoff points over line-by-line paraphrase.\n"
            "- Do not skip an upstream step if the query explicitly asks for the flow from the start.\n"
            "- If the query names a concrete interface, anchor the answer at that named interface instead of inventing a broader caller chain.\n"
            "- Do not climb to unrelated callers or setup code unless the question explicitly asks for the earlier caller and the context shows it.\n"
            "- Keep configuration details out of the flow unless the query explicitly asks for configuration.\n"
        )
        if query_identifiers:
            enforcement_parts.append(
                "FLOW ANCHOR RULE:\n"
                f"- The query names these concrete interfaces: {', '.join(query_identifiers[:4])}.\n"
                "- Start from the nearest named interface shown by the evidence.\n"
            )
        if not query_requests_configuration:
            enforcement_parts.append(
                "FLOW CONFIGURATION RULE:\n"
                "- Do not add secret keys, algorithms, default values, or environment/setup constants unless they are necessary to answer the asked flow.\n"
            )
        if wants_entry and has_entry_evidence:
            enforcement_parts.append(
                "FLOW ENTRY EVIDENCE RULE:\n"
                "- The retrieved context includes upstream entry evidence such as wrappers, decorators, middleware, request parsing, or header extraction.\n"
                "- Cover that entry evidence before describing deeper validation or business logic.\n"
            )
        if wants_entry and not has_entry_evidence:
            enforcement_parts.append(
                "FLOW EVIDENCE LIMITATION:\n"
                "- If the retrieved context does not show the upstream entry point directly, say that explicitly in the entry section.\n"
                "- Do not relabel a later validation or transformation step as the entry point.\n"
            )
        structure_sections.extend(
            [
                "## Entry / Start",
                "## Validation / Transformation",
                "## Downstream Use",
                "## Failure Paths",
            ]
        )
    elif query_class == "comparison":
        enforcement_parts.append(
            "COMPARISON CONTRACT:\n"
            "- Compare the asked alternatives directly rather than describing them in isolation.\n"
            "- Cover what is implemented, what is only conceptual if relevant, practical tradeoffs, and how the alternatives interact if the question asks for combinations.\n"
            "- For each alternative discussed, include at least one practical consequence or usage scenario.\n"
            "- Answer the core contrast first. Mention extra methods or neighboring components only if they materially change the asked comparison.\n"
        )
        if comparison_items:
            enforcement_parts.append(
                "COMPARISON COVERAGE RULE:\n"
                f"- The query names these alternatives: {', '.join(comparison_items)}.\n"
                "- Cover each named alternative explicitly, even if one is not implemented in the repo.\n"
                "- For each named alternative, include status in repo, one use case, and one drawback.\n"
                "- If the query asks when to use each, include one short example or scenario for each named alternative.\n"
            )
        enforcement_parts.append(
            "CONTRAST FOCUS RULE:\n"
            "- Stay focused on the named alternatives and their exact differences.\n"
            "- Mention adjacent methods, APIs, or components only if they materially change the asked contrast.\n"
        )
        structure_sections.extend(
            [
                "## What Is Implemented",
                "## Key Differences",
                "## Practical Tradeoffs",
                "## Combination / Interaction Notes",
            ]
        )
        if query_requests_examples:
            structure_sections.append("## Short Usage Examples")
    elif query_class == "system_scope":
        enforcement_parts.append(
            "SYSTEM-SCOPE CONTRACT:\n"
            "- Cover the behavior across the system, not just one function.\n"
            "- Include where handling occurs, what is implemented, what is missing, and how failures or missing behavior propagate.\n"
            "- If the retrieved context spans multiple files or layers, reflect that broader scope.\n"
            "- Do not collapse a system-level question to a single local implementation detail.\n"
            "- Keep cross-file coverage semantically aligned to the asked mechanism. Do not import unrelated fallback examples just because they also mention errors, parsing, or recovery.\n"
        )
        if unique_files >= 3:
            enforcement_parts.append(
                "SYSTEM-SCOPE EVIDENCE RULE:\n"
                "- The retrieved context spans multiple files. Prefer a cross-layer answer over a single-module answer.\n"
            )
        if focus_terms:
            enforcement_parts.append(
                "SYSTEM-SCOPE LOCALITY RULE:\n"
                f"- Keep the answer centered on evidence aligned with these focus terms: {', '.join(focus_terms)}.\n"
                "- Exclude tangential subsystems unless they directly implement the asked behavior.\n"
            )
        structure_sections.extend(
            [
                "## Where It Happens",
                "## What Is Implemented",
                "## What Is Missing",
                "## Propagation / Failure Behavior",
                "## Practical Improvement Options",
            ]
        )
    elif query_class == "interaction":
        enforcement_parts.append(
            "INTERACTION CONTRACT:\n"
            "- Explain the interaction or priority order first: what happens, in what order, and why that outcome occurs.\n"
            "- Prefer direct effects and execution order over helper-method internals.\n"
            "- Include one compact example only if it clarifies the interaction.\n"
            "- Do not expand into low-value internal heuristics, mock values, or helper details unless the question explicitly asks for them.\n"
            "- If inference is necessary, label it inline briefly instead of adding a separate meta-analysis section.\n"
            "- Do not use hypothetical helper return values, fabricated filter outcomes, or made-up mini-scenarios to illustrate the answer.\n"
            "- If a compact example cannot be stated directly from the observed behavior, omit the example rather than inventing one.\n"
        )
        if has_cache_evidence or has_timing_evidence or has_cost_evidence:
            evidence_bits: list[str] = []
            if has_cache_evidence:
                evidence_bits.append("cache short-circuiting")
            if has_timing_evidence:
                evidence_bits.append("timing or metrics recording")
            if has_cost_evidence:
                evidence_bits.append("cost estimation")
            enforcement_parts.append(
                "INTERACTION EVIDENCE DEPTH RULE:\n"
                f"- The retrieved context shows evidence for {', '.join(evidence_bits)}.\n"
                "- Place those phases explicitly in the interaction flow instead of leaving them implicit.\n"
                "- If the evidence supports a concrete multi-step path, include exactly one compact evidence-backed example.\n"
            )
        structure_sections.extend(
            [
                "## Core Interaction",
                "## Order / Priority",
                "## Why That Outcome Happens",
                "## Compact Example",
            ]
        )

    if query_mentions_named_rules:
        enforcement_parts.append(
            "NAMED MECHANISM EXACTNESS RULE:\n"
            "- If the query names concrete rules, methods, or components, map each named item to the exact observed method or behavior in the retrieved context.\n"
            "- Describe the observed transformation or ordering from code, not the generic textbook meaning of the name.\n"
            "- If the retrieved code shows a narrower implementation than the conventional definition, answer with the narrower implementation.\n"
            "- Do not upgrade a literal check, sort, or helper branch into a more general algorithm unless the code explicitly shows that algorithm.\n"
        )

    if query_requests_numeric_mechanism:
        enforcement_parts.append(
            "NUMERIC MECHANISM RULE:\n"
            "- For numeric, scoring, or NaN-style questions, explain the underlying formula or numeric cause first when the context supports it.\n"
            "- Then explain how the code detects, combines, filters, clamps, or reports that numeric behavior.\n"
            "- If an exact formula is not shown, say that directly and stay with the observed code path instead of inventing one.\n"
            "- Do not substitute only operational handling when the query explicitly asks what causes the numeric outcome.\n"
        )

    if query_requests_interface_exactness:
        enforcement_parts.append(
            "INTERFACE EXACTNESS RULE:\n"
            "- For storage, serialization, or retry questions, prefer the concrete public API surface, explicit parameters, branches, and key formats shown in context.\n"
            "- Do not invent hidden helper methods, automatic fallback layers, or internal serializer abstractions unless they are directly shown.\n"
            "- If retries or fallback behavior are not implemented in the shown interface, say that explicitly instead of describing a typical design.\n"
        )

    unique_sections: list[str] = []
    seen = set()
    for section in structure_sections:
        if section in seen:
            continue
        seen.add(section)
        unique_sections.append(section)

    structure_prompt = (
        "Additional Answer Structure Requirements:\n"
        + "\n".join(unique_sections)
        + "\n- Use only sections that are applicable to the actual evidence.\n"
        + "- If a section is included, provide substantive content.\n"
    ) if unique_sections else ""

    completion_prompt = (
        "Additional Completion Rule:\n"
        "- Once you have covered the required labeled sections for this answer shape, stop without adding speculative appendices.\n"
    ) if unique_sections else ""

    return AnswerShapeContract(
        enforcement_prompt="\n\n".join(enforcement_parts).strip(),
        structure_prompt=structure_prompt.strip(),
        completion_prompt=completion_prompt.strip(),
        query_class=query_class,
        absent_code_mode=absent_code_mode,
    )
