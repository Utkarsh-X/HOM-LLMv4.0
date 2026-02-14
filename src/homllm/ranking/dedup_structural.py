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

    def deduplicate(self, candidates: list[Candidate]) -> list[Candidate]:
        if not candidates:
            return []

        prefer_coarse = self._prefer_coarse(candidates)

        kept: list[Candidate | None] = []
        index_by_symbol: dict[str, int] = {}
        children_by_parent: dict[str, set[int]] = {}
        spans_by_file: dict[str, list[tuple[int, int, int]]] = {}

        for candidate in candidates:
            if candidate.symbol_id and candidate.symbol_id in index_by_symbol:
                continue

            parent_id = candidate.parent_symbol_id
            if parent_id and parent_id in index_by_symbol:
                parent_idx = index_by_symbol[parent_id]
                if self._prefer_candidate(
                    candidate, kept[parent_idx], prefer_coarse
                ):
                    self._replace(
                        parent_idx,
                        candidate,
                        kept,
                        index_by_symbol,
                        children_by_parent,
                        spans_by_file,
                    )
                continue

            if candidate.symbol_id:
                child_indices = children_by_parent.get(candidate.symbol_id)
                if child_indices:
                    if prefer_coarse:
                        earliest_idx = min(child_indices)
                        for idx in list(child_indices):
                            self._remove(
                                idx, kept, index_by_symbol, children_by_parent
                            )
                        self._insert_at(
                            earliest_idx,
                            candidate,
                            kept,
                            index_by_symbol,
                            children_by_parent,
                            spans_by_file,
                        )
                    continue

            if self._overlaps(candidate, kept, spans_by_file):
                continue

            idx = len(kept)
            kept.append(candidate)
            self._register(
                idx, candidate, index_by_symbol, children_by_parent, spans_by_file
            )

        return [c for c in kept if c is not None]

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
        self, candidate: Candidate, existing: Candidate | None, prefer_coarse: bool
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

    def _overlaps(
        self,
        candidate: Candidate,
        kept: list[Candidate | None],
        spans_by_file: dict[str, list[tuple[int, int, int]]],
    ) -> bool:
        if not candidate.file:
            return False
        if candidate.span_start is None or candidate.span_end is None:
            return False
        for start, end, idx in spans_by_file.get(candidate.file, []):
            if idx >= len(kept) or kept[idx] is None:
                continue
            if start <= candidate.span_end and end >= candidate.span_start:
                return True
        return False

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
        if (
            candidate.file
            and candidate.span_start is not None
            and candidate.span_end is not None
        ):
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
            idx, candidate, kept, index_by_symbol, children_by_parent, spans_by_file
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
            idx, candidate, index_by_symbol, children_by_parent, spans_by_file
        )


__all__ = ["StructuralDeduplicator"]
