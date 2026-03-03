"""Structural deduplication for ranking."""

from __future__ import annotations

import math
from collections import Counter

from homllm.retrieval.interfaces import Candidate

_GRANULARITY_RANK = {"fine": 3, "medium": 2, "coarse": 1}


class StructuralDeduplicator:
    """Deduplicate candidates using spans and symbol hierarchy."""

    def __init__(self, file_entropy_threshold: float = 0.6):
        self.file_entropy_threshold = file_entropy_threshold
        self.last_trace: list[dict[str, object]] = []
        self.last_meta: dict[str, object] = {}

    def deduplicate(self, candidates: list[Candidate]) -> list[Candidate]:
        self.last_trace = []
        self.last_meta = {}

        if not candidates:
            self.last_meta = {"input_count": 0, "output_count": 0, "prefer_coarse": False}
            return []

        prefer_coarse = self._prefer_coarse(candidates)
        self.last_meta = {
            "input_count": len(candidates),
            "prefer_coarse": bool(prefer_coarse),
        }

        kept: list[Candidate | None] = []
        index_by_symbol: dict[str, int] = {}
        children_by_parent: dict[str, set[int]] = {}
        spans_by_file: dict[str, list[tuple[int, int, int]]] = {}

        for candidate in candidates:
            if candidate.symbol_id and candidate.symbol_id in index_by_symbol:
                existing = kept[index_by_symbol[candidate.symbol_id]]
                self._record_decision(
                    candidate,
                    action="skip",
                    reason="duplicate_symbol_id",
                    replaced_candidate_id=getattr(existing, "doc_id", None),
                )
                continue

            parent_id = candidate.parent_symbol_id
            if parent_id and parent_id in index_by_symbol:
                parent_idx = index_by_symbol[parent_id]
                existing = kept[parent_idx]
                if self._prefer_candidate(candidate, existing, prefer_coarse):
                    self._replace(
                        parent_idx,
                        candidate,
                        kept,
                        index_by_symbol,
                        children_by_parent,
                        spans_by_file,
                    )
                    self._record_decision(
                        candidate,
                        action="replace",
                        reason="replace_parent_symbol_block",
                        replaced_candidate_id=getattr(existing, "doc_id", None),
                    )
                else:
                    self._record_decision(
                        candidate,
                        action="skip",
                        reason="parent_symbol_block_preferred",
                        replaced_candidate_id=getattr(existing, "doc_id", None),
                    )
                continue

            if candidate.symbol_id:
                child_indices = children_by_parent.get(candidate.symbol_id)
                if child_indices:
                    if prefer_coarse:
                        replaced_ids: list[str] = []
                        earliest_idx = min(child_indices)
                        for idx in list(child_indices):
                            existing = kept[idx] if idx < len(kept) else None
                            if existing is not None:
                                replaced_ids.append(existing.doc_id)
                            self._remove(idx, kept, index_by_symbol, children_by_parent)
                        self._insert_at(
                            earliest_idx,
                            candidate,
                            kept,
                            index_by_symbol,
                            children_by_parent,
                            spans_by_file,
                        )
                        self._record_decision(
                            candidate,
                            action="replace",
                            reason="replace_children_with_parent",
                            replaced_candidate_ids=replaced_ids,
                        )
                    else:
                        child_ids = [
                            kept[idx].doc_id
                            for idx in child_indices
                            if idx < len(kept) and kept[idx] is not None
                        ]
                        self._record_decision(
                            candidate,
                            action="skip",
                            reason="child_blocks_preferred",
                            replaced_candidate_ids=child_ids,
                        )
                    continue

            # Check span overlap while preferring finer granularity over coarser.
            overlap_result, overlap_reason, overlap_replaced = self._check_overlap_and_replace(
                candidate,
                kept,
                index_by_symbol,
                children_by_parent,
                spans_by_file,
            )
            if overlap_result == "skip":
                self._record_decision(
                    candidate,
                    action="skip",
                    reason=overlap_reason or "span_overlap_skip",
                    replaced_candidate_id=overlap_replaced,
                )
                continue
            if overlap_result == "added":
                self._record_decision(
                    candidate,
                    action="replace",
                    reason=overlap_reason or "span_overlap_replace",
                    replaced_candidate_id=overlap_replaced,
                )

            idx = len(kept)
            kept.append(candidate)
            self._register(
                idx,
                candidate,
                index_by_symbol,
                children_by_parent,
                spans_by_file,
            )
            self._record_decision(candidate, action="keep", reason="insert_no_overlap")

        result = [c for c in kept if c is not None]

        # Post-pass: drop coarse/summary blocks from files that also have fine blocks.
        result = self._drop_coarse_when_fine_exists(result)
        self.last_meta["output_count"] = len(result)

        return result

    # --------------------------------------------------------------------- #
    # Post-pass: coarse -> fine preference                                  #
    # --------------------------------------------------------------------- #
    def _drop_coarse_when_fine_exists(self, candidates: list[Candidate]) -> list[Candidate]:
        """Remove coarse blocks from files that also have fine blocks."""
        import logging

        logger = logging.getLogger(__name__)

        files_with_fine: set[str] = set()
        for c in candidates:
            level = (c.granularity_level or "").lower()
            if level == "fine" and c.file:
                files_with_fine.add(c.file)

        if not files_with_fine:
            return candidates

        filtered: list[Candidate] = []
        for c in candidates:
            level = (c.granularity_level or "").lower()
            if level == "coarse" and c.file in files_with_fine:
                logger.info(
                    "[DEDUP] Dropping coarse block %s L%s-%s (fine blocks exist for same file)",
                    c.file,
                    c.span_start,
                    c.span_end,
                )
                self._record_decision(
                    c,
                    action="drop",
                    reason="postpass_drop_coarse_when_fine_exists",
                )
                continue
            filtered.append(c)

        return filtered

    def _prefer_coarse(self, candidates: list[Candidate]) -> bool:
        files = [c.file for c in candidates if c.file]
        if len(files) <= 1:
            return False

        counts = Counter(files)
        total = sum(counts.values())
        if total <= 0:
            return False

        probs = [count / total for count in counts.values()]
        entropy = -sum(p * math.log(p) for p in probs)
        max_entropy = math.log(len(counts))
        normalized = entropy / max_entropy if max_entropy > 0 else 0.0
        return normalized >= self.file_entropy_threshold

    def _granularity_rank(self, candidate: Candidate) -> int:
        level = (candidate.granularity_level or "").lower()
        return _GRANULARITY_RANK.get(level, 0)

    def _prefer_candidate(
        self,
        candidate: Candidate,
        existing: Candidate | None,
        prefer_coarse: bool,
    ) -> bool:
        if existing is None:
            return True
        candidate_rank = self._granularity_rank(candidate)
        existing_rank = self._granularity_rank(existing)
        if candidate_rank == existing_rank:
            return False
        if prefer_coarse:
            return candidate_rank < existing_rank
        return candidate_rank > existing_rank

    def _check_overlap_and_replace(
        self,
        candidate: Candidate,
        kept: list[Candidate | None],
        index_by_symbol: dict[str, int],
        children_by_parent: dict[str, set[int]],
        spans_by_file: dict[str, list[tuple[int, int, int]]],
    ) -> tuple[str, str | None, str | None]:
        """Check overlap with granularity-aware replacement."""
        import logging

        _logger = logging.getLogger(__name__)

        if not candidate.file:
            return "no_overlap", None, None
        if candidate.span_start is None or candidate.span_end is None:
            return "no_overlap", None, None

        cand_level = (candidate.granularity_level or "").lower()
        cand_rank = _GRANULARITY_RANK.get(cand_level, 0)

        for start, end, idx in list(spans_by_file.get(candidate.file, [])):
            if idx >= len(kept) or kept[idx] is None:
                continue
            if not (start <= candidate.span_end and end >= candidate.span_start):
                continue

            existing = kept[idx]
            existing_level = (existing.granularity_level or "").lower()
            existing_rank = _GRANULARITY_RANK.get(existing_level, 0)

            if cand_rank > existing_rank:
                spans_by_file[candidate.file] = [
                    (s, e, i)
                    for s, e, i in spans_by_file.get(candidate.file, [])
                    if i != idx
                ]
                self._remove(idx, kept, index_by_symbol, children_by_parent)
                self._insert_at(
                    idx,
                    candidate,
                    kept,
                    index_by_symbol,
                    children_by_parent,
                    spans_by_file,
                )
                _logger.info(
                    "[DEDUP] Replaced %s block %s L%s-%s with %s block L%s-%s",
                    existing_level,
                    candidate.file,
                    start,
                    end,
                    cand_level,
                    candidate.span_start,
                    candidate.span_end,
                )
                return (
                    "added",
                    "replace_coarser_overlapping_span",
                    getattr(existing, "doc_id", None),
                )

            return (
                "skip",
                "skip_overlapping_span_not_finer",
                getattr(existing, "doc_id", None),
            )

        return "no_overlap", None, None

    def _record_decision(
        self,
        candidate: Candidate,
        *,
        action: str,
        reason: str,
        replaced_candidate_id: str | None = None,
        replaced_candidate_ids: list[str] | None = None,
    ) -> None:
        self.last_trace.append(
            {
                "doc_id": candidate.doc_id,
                "symbol_id": candidate.symbol_id,
                "file": candidate.file,
                "action": action,
                "reason": reason,
                "replaced_candidate_id": replaced_candidate_id,
                "replaced_candidate_ids": list(replaced_candidate_ids or []),
            }
        )

    def _register(
        self,
        idx: int,
        candidate: Candidate,
        index_by_symbol: dict[str, int],
        children_by_parent: dict[str, set[int]],
        spans_by_file: dict[str, list[tuple[int, int, int]]],
    ) -> None:
        if candidate.symbol_id:
            index_by_symbol[candidate.symbol_id] = idx
        if candidate.parent_symbol_id:
            children_by_parent.setdefault(candidate.parent_symbol_id, set()).add(idx)
        if candidate.file and candidate.span_start is not None and candidate.span_end is not None:
            spans_by_file.setdefault(candidate.file, []).append(
                (candidate.span_start, candidate.span_end, idx)
            )

    def _remove(
        self,
        idx: int,
        kept: list[Candidate | None],
        index_by_symbol: dict[str, int],
        children_by_parent: dict[str, set[int]],
    ) -> None:
        if idx >= len(kept):
            return
        candidate = kept[idx]
        if candidate is None:
            return
        if candidate.symbol_id:
            index_by_symbol.pop(candidate.symbol_id, None)
        if candidate.parent_symbol_id:
            children_by_parent.get(candidate.parent_symbol_id, set()).discard(idx)
        kept[idx] = None

    def _replace(
        self,
        idx: int,
        candidate: Candidate,
        kept: list[Candidate | None],
        index_by_symbol: dict[str, int],
        children_by_parent: dict[str, set[int]],
        spans_by_file: dict[str, list[tuple[int, int, int]]],
    ) -> None:
        self._remove(idx, kept, index_by_symbol, children_by_parent)
        self._insert_at(
            idx,
            candidate,
            kept,
            index_by_symbol,
            children_by_parent,
            spans_by_file,
        )

    def _insert_at(
        self,
        idx: int,
        candidate: Candidate,
        kept: list[Candidate | None],
        index_by_symbol: dict[str, int],
        children_by_parent: dict[str, set[int]],
        spans_by_file: dict[str, list[tuple[int, int, int]]],
    ) -> None:
        kept[idx] = candidate
        self._register(
            idx,
            candidate,
            index_by_symbol,
            children_by_parent,
            spans_by_file,
        )


__all__ = ["StructuralDeduplicator"]
