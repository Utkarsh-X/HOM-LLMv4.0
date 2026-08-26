"""Shared seed-evidence helpers for patch planners.

Extracted verbatim from ``provider_patch_planner.py`` so both the single-shot
planner and the agentic-loop planner build identical target evidence packs
(section-scan fallback, per-target evidence context, retrieval scoring).
"""

import hashlib
from pathlib import Path

from homllm_v4.contracts.evidence import EvidenceCandidate, EvidenceSet
from homllm_v4.contracts.edit_proposal import EditProposalEvidenceContext
from homllm_v4.planning.target_section_scanner import scan_target_sections


def hash_text(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def preserve_original_trailing_newline(new_content: str, old_content: str) -> str:
    if old_content.endswith("\n") and not new_content.endswith("\n"):
        return f"{new_content}\n"
    return new_content


def best_retrieval_score(
    candidates: tuple[EvidenceCandidate, ...],
    target_file: str,
) -> float | None:
    scores = [
        candidate.retrieval_score
        for candidate in candidates
        if candidate.file_path == target_file and candidate.retrieval_score is not None
    ]
    if not scores:
        return None
    return max(scores)


def evidence_context_for_target(
    evidence_set: EvidenceSet,
    target_file: str,
) -> tuple[EditProposalEvidenceContext, ...]:
    return tuple(
        EditProposalEvidenceContext(
            evidence_id=candidate.candidate_id,
            file_path=candidate.file_path,
            span_start=candidate.span_start,
            span_end=candidate.span_end,
            content=str(candidate.metadata.get("content") or ""),
        )
        for candidate in evidence_set.candidates
        if candidate.file_path == target_file
    )


def build_target_section_fallback_candidates(
    *,
    target_file: str,
    content: str,
    query: str,
    context: str,
    full_content_hash: str,
) -> tuple[EvidenceCandidate, ...]:
    """Build target-file evidence from a section scan when retrieval missed it.

    The previous fallback was a single candidate holding the *entire* file,
    which the evidence renderer truncated to its first ~2000 chars (the
    import header). Instead, scan the file for query-relevant sections and
    emit each as a candidate with a real line span, so the model sees e.g.
    ``[target-section-1] complexes.py:400-479`` with actual code rather than
    a useless header. Falls back to the old full-file candidate only when the
    scan finds nothing (e.g. no query token appears in the file).
    """
    sections = scan_target_sections(
        content,
        query=query,
        context=context,
    )
    if sections:
        return tuple(
            EvidenceCandidate(
                candidate_id=f"target-section-{index}",
                file_path=target_file,
                symbol_id=None,
                span_start=section.span_start,
                span_end=section.span_end,
                content_hash=hash_text(section.content),
                source_channels=("target_section_scan",),
                bm25_score=None,
                vector_score=None,
                graph_score=None,
                retrieval_score=float(section.score),
                metadata={
                    "content": section.content,
                    "target_section_scan": True,
                    "section_score": section.score,
                },
            )
            for index, section in enumerate(sections)
        )
    safe_target = target_file.replace('/', '_').replace('\\', '_').replace('.', '_')
    return (
        EvidenceCandidate(
            candidate_id=f"fallback-{safe_target}",
            file_path=target_file,
            symbol_id=None,
            span_start=1,
            span_end=None,
            content_hash=full_content_hash,
            source_channels=("direct_read_fallback",),
            bm25_score=1.0,
            vector_score=None,
            graph_score=None,
            retrieval_score=1.0,
            metadata={"content": content},
        ),
    )


def resolve_seed_evidence_bundle(
    *,
    workspace_root: str | Path,
    target_file: str,
    candidates: tuple[EvidenceCandidate, ...],
    query: str,
    intent: str,
    expected_behavior: str,
    direct_read_output,
) -> tuple[tuple[EvidenceCandidate, ...], bool, float | None]:
    """Return ``(evidence_candidates_for_target, retrieved_flag, best_score)``.

    When retrieval produced no candidate for the target file this synthesizes
    section-scan fallback candidates from the direct read so the model sees
    real code spans instead of an import header. ``direct_read_output`` is the
    ``DirectReadResult`` from ``DirectReadService.read``.
    """
    has_evidence_for_target = any(
        candidate.file_path == target_file for candidate in candidates
    )
    if has_evidence_for_target:
        return (
            tuple(candidate for candidate in candidates if candidate.file_path == target_file),
            True,
            best_retrieval_score(candidates, target_file),
        )
    fallback = build_target_section_fallback_candidates(
        target_file=target_file,
        content=direct_read_output.content_excerpt or "",
        query=query,
        context=" ".join((intent, expected_behavior)),
        full_content_hash=direct_read_output.content_hash or "",
    )
    return (fallback, False, None)
