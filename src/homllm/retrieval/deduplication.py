"""Hierarchical deduplication for parent/child chunk overlap."""

from __future__ import annotations

from collections import defaultdict

from homllm.common.types import Intent
from homllm.retrieval.interfaces import Candidate


_RANK = {"fine": 3, "medium": 2, "coarse": 1}


def deduplicate_hierarchical(
    candidates: list[Candidate],
    intent: Intent | None = None,
) -> list[Candidate]:
    """
    Remove broad parent chunks when finer chunks from the same file exist.

    Rules:
    - If fine exists for file, drop coarse for that file.
    - If >=2 fine exists for file, drop medium for that file.

    Intent-aware adjustment:
    - For explanatory/search queries, keep one medium and one coarse block per file
      to preserve architectural context.
    """
    if not candidates:
        return candidates

    by_file: dict[str, list[Candidate]] = defaultdict(list)
    passthrough: list[Candidate] = []
    for candidate in candidates:
        file_key = candidate.file or ""
        if not file_key:
            passthrough.append(candidate)
            continue
        by_file[file_key].append(candidate)

    keep_structural_context = intent in {Intent.EXPLAIN, Intent.SEARCH}

    deduped: list[Candidate] = []
    for file_candidates in by_file.values():
        fine_count = sum(
            1 for candidate in file_candidates if (candidate.granularity_level or "").lower() == "fine"
        )
        best_medium = None
        best_coarse = None
        if keep_structural_context:
            for candidate in sorted(file_candidates, key=lambda c: c.hybrid_score, reverse=True):
                level = (candidate.granularity_level or "").lower()
                if best_medium is None and level == "medium":
                    best_medium = candidate.doc_id
                if best_coarse is None and level == "coarse":
                    best_coarse = candidate.doc_id
                if best_medium is not None and best_coarse is not None:
                    break

        for candidate in sorted(file_candidates, key=lambda c: c.hybrid_score, reverse=True):
            level = (candidate.granularity_level or "").lower()
            if (
                keep_structural_context
                and level == "medium"
                and candidate.doc_id == best_medium
            ):
                deduped.append(candidate)
                continue
            if (
                keep_structural_context
                and level == "coarse"
                and candidate.doc_id == best_coarse
            ):
                deduped.append(candidate)
                continue

            if level == "coarse" and fine_count > 0:
                continue
            if level == "medium" and fine_count >= 2:
                continue
            deduped.append(candidate)

    deduped.extend(passthrough)
    deduped.sort(
        key=lambda c: (c.hybrid_score, _RANK.get((c.granularity_level or "").lower(), 0)),
        reverse=True,
    )
    return deduped
