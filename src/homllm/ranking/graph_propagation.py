"""Graph propagation for two-pass ranking."""

from __future__ import annotations

from collections import deque


class NeighborBoosting:
    """Neighbor boosting with exponential decay."""

    def __init__(self, callgraph: dict | None, max_depth: int = 3, decay: float = 0.8):
        self.max_depth = max_depth
        self.decay = decay
        self._adj = self._build_adjacency(callgraph or {})

    def _build_adjacency(self, callgraph: dict) -> dict[str, set[str]]:
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

        for node, neighbors in callgraph.items():
            if not isinstance(neighbors, (list, tuple, set)):
                continue
            adj.setdefault(str(node), set()).update(str(n) for n in neighbors)
        return adj

    def propagate(self, seeds: dict[str, float]) -> dict[str, float]:
        if not self._adj or not seeds:
            return {}

        scores: dict[str, float] = dict(seeds)
        queue: deque[tuple[str, int, float]] = deque(
            (node, 0, score) for node, score in seeds.items()
        )
        seen: set[tuple[str, int]] = set()

        while queue:
            node, depth, score = queue.popleft()
            if depth >= self.max_depth:
                continue
            for neigh in self._adj.get(node, ()):
                key = (neigh, depth + 1)
                if key in seen:
                    continue
                seen.add(key)
                propagated = score * (self.decay ** (depth + 1))
                if propagated <= 0:
                    continue
                if propagated > scores.get(neigh, 0.0):
                    scores[neigh] = propagated
                queue.append((neigh, depth + 1, score))

        return scores


__all__ = ["NeighborBoosting"]
