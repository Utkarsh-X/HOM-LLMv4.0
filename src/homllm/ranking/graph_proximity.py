"""Graph proximity scoring for ranking."""

from __future__ import annotations

from collections import deque
from typing import Iterable

from homllm.retrieval.interfaces import Candidate


class GraphProximity:
    """Compute distance-aware structural relevance from a call graph."""

    def __init__(self, callgraph: dict | None, max_depth: int = 4, anchor_k: int = 5):
        self.max_depth = max_depth
        self.anchor_k = anchor_k
        self._adj = self._build_adjacency(callgraph or {})

    def _build_adjacency(self, callgraph: dict) -> dict[str, set[str]]:
        """
        Normalize callgraph to adjacency map.

        Supports:
        - {"edges": [{"caller_id":..., "callee_id":...}, ...]}
        - {symbol_id: [neighbors]} (already adjacency)
        """
        adj: dict[str, set[str]] = {}
        edges = callgraph.get("edges")
        if isinstance(edges, list):
            for edge in edges:
                caller = edge.get("caller_id")
                callee = edge.get("callee_id")
                if not caller or not callee:
                    continue
                adj.setdefault(caller, set()).add(callee)
                adj.setdefault(callee, set()).add(caller)
            return adj

        # Assume adjacency-like mapping
        for node, neighbors in callgraph.items():
            if not isinstance(neighbors, (list, tuple, set)):
                continue
            adj.setdefault(str(node), set()).update(str(n) for n in neighbors)
        return adj

    def compute_distance_map(self, candidates: list[Candidate]) -> dict[str, int]:
        """Return min graph distance from anchors to each symbol."""
        if not self._adj:
            return {}

        anchors = self._select_anchors(candidates)
        if not anchors:
            return {}

        distances: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque((a, 0) for a in anchors)
        seen = set(anchors)

        while queue:
            node, dist = queue.popleft()
            distances[node] = min(distances.get(node, dist), dist)
            if dist >= self.max_depth:
                continue
            for neigh in self._adj.get(node, ()):
                if neigh in seen:
                    continue
                seen.add(neigh)
                queue.append((neigh, dist + 1))

        return distances

    def distance_to_score(self, distance: int | None) -> float:
        """Map graph distance to continuous score in [0, 1]."""
        if distance is None:
            return 0.0
        if distance <= 0:
            return 1.0
        if distance == 1:
            return 0.8
        if distance == 2:
            return 0.6
        if distance == 3:
            return 0.4
        return 0.2

    def _select_anchors(self, candidates: list[Candidate]) -> set[str]:
        """Anchor symbols from top-K bm25 and vector candidates."""
        anchors: set[str] = set()
        if not candidates:
            return anchors

        by_bm25 = sorted(
            [c for c in candidates if c.symbol_id],
            key=lambda c: c.bm25_score,
            reverse=True,
        )
        by_vec = sorted(
            [c for c in candidates if c.symbol_id],
            key=lambda c: c.vector_score,
            reverse=True,
        )

        for c in by_bm25[: self.anchor_k]:
            if c.symbol_id:
                anchors.add(c.symbol_id)
        for c in by_vec[: self.anchor_k]:
            if c.symbol_id:
                anchors.add(c.symbol_id)
        return anchors


__all__ = ["GraphProximity"]

