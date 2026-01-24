"""
Level-3 Cognitive Graph

Reasoning-topology graph for cognitive shaping.
This models reasoning flow, NOT semantic relationships.

Node types represent reasoning elements.
Edge types represent reasoning relationships.

CONSTRAINTS (ABSOLUTE):
- ≤80 nodes per query
- ≤4 edges per node
- Max depth: 5
- In-memory only, no persistence
- No LLM or ML
- Deterministic
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Iterator
from collections import deque


class CognitiveNodeType(Enum):
    """Types of nodes in the cognitive graph."""
    
    REASONING_STEP = "reasoning_step"       # A step in reasoning
    DECISION_POINT = "decision_point"       # Branching decision
    INVARIANT = "invariant"                 # Constraint that must hold
    ASSUMPTION = "assumption"               # Assumed context
    EXPLANATION_ANCHOR = "explanation_anchor"  # Explanation grounding point
    STATE_TRANSITION = "state_transition"   # State change point


class CognitiveEdgeType(Enum):
    """Types of edges in the cognitive graph."""
    
    LEADS_TO = "leads_to"       # A leads to B in reasoning
    DEPENDS_ON = "depends_on"   # A depends on B
    CONSTRAINS = "constrains"   # A constrains B
    EXPLAINS = "explains"       # A explains B
    BRANCHES = "branches"       # A branches to B (decision)
    STABILIZES = "stabilizes"   # A stabilizes B (invariant)


@dataclass(frozen=True)
class CognitiveNode:
    """
    A node in the cognitive graph.
    
    Represents a reasoning element.
    """
    
    node_id: str
    node_type: CognitiveNodeType
    label: str
    block_id: Optional[str] = None  # Associated context block
    depth: int = 0                   # Depth in reasoning tree
    complexity: int = 0              # Local complexity score
    metadata: tuple[tuple[str, Any], ...] = ()
    
    @property
    def meta_dict(self) -> dict[str, Any]:
        """Convert metadata to dict."""
        return dict(self.metadata)
    
    @property
    def is_decision(self) -> bool:
        """Check if this is a decision point."""
        return self.node_type == CognitiveNodeType.DECISION_POINT
    
    @property
    def is_anchor(self) -> bool:
        """Check if this is an explanation anchor."""
        return self.node_type == CognitiveNodeType.EXPLANATION_ANCHOR


@dataclass(frozen=True)
class CognitiveEdge:
    """
    An edge in the cognitive graph.
    
    Directed: source → target in reasoning flow.
    """
    
    source_id: str
    target_id: str
    edge_type: CognitiveEdgeType
    weight: float = 1.0  # Edge importance (0.0 - 1.0)


class CognitiveGraph:
    """
    Reasoning-topology graph for cognitive shaping.
    
    Models reasoning flow: how concepts connect to form understanding.
    NOT a semantic graph (that's Level-2).
    
    Key differences from SemanticGraph:
    - Focused on REASONING FLOW, not semantic relationships
    - Tracks decision points and branching
    - Tracks invariants and anchors
    - Lower node limit (80 vs 200)
    - Lower edge limit (4 vs 5)
    - Higher depth limit (5 vs 2)
    
    Constraints:
    - Max 80 nodes
    - Max 4 edges per node
    - Max depth 5
    """
    
    MAX_NODES = 80
    MAX_EDGES_PER_NODE = 4
    MAX_DEPTH = 5
    
    def __init__(self):
        self._nodes: dict[str, CognitiveNode] = {}
        self._edges: list[CognitiveEdge] = []
        self._outgoing: dict[str, list[CognitiveEdge]] = {}
        self._incoming: dict[str, list[CognitiveEdge]] = {}
        self._entry_nodes: list[str] = []  # Entry points for reasoning
        self._anchor_nodes: list[str] = []  # Explanation anchors
    
    @property
    def node_count(self) -> int:
        return len(self._nodes)
    
    @property
    def edge_count(self) -> int:
        return len(self._edges)
    
    @property
    def entry_points(self) -> list[str]:
        """Get reasoning entry points."""
        return list(self._entry_nodes)
    
    @property
    def anchors(self) -> list[str]:
        """Get explanation anchors."""
        return list(self._anchor_nodes)
    
    def add_node(
        self,
        node_id: str,
        node_type: CognitiveNodeType,
        label: str,
        block_id: Optional[str] = None,
        depth: int = 0,
        complexity: int = 0,
        metadata: Optional[dict[str, Any]] = None,
        is_entry: bool = False,
    ) -> bool:
        """
        Add a node to the graph.
        
        Returns False if limit exceeded or node exists.
        """
        if node_id in self._nodes:
            return False
        
        if len(self._nodes) >= self.MAX_NODES:
            return False
        
        # Enforce max depth
        if depth > self.MAX_DEPTH:
            depth = self.MAX_DEPTH
        
        meta_tuple = tuple(sorted(metadata.items())) if metadata else ()
        node = CognitiveNode(
            node_id=node_id,
            node_type=node_type,
            label=label,
            block_id=block_id,
            depth=depth,
            complexity=complexity,
            metadata=meta_tuple,
        )
        
        self._nodes[node_id] = node
        self._outgoing[node_id] = []
        self._incoming[node_id] = []
        
        # Track special nodes
        if is_entry:
            self._entry_nodes.append(node_id)
        if node_type == CognitiveNodeType.EXPLANATION_ANCHOR:
            self._anchor_nodes.append(node_id)
        
        return True
    
    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: CognitiveEdgeType,
        weight: float = 1.0,
    ) -> bool:
        """
        Add an edge to the graph.
        
        Returns False if nodes don't exist or edge limit exceeded.
        """
        if source_id not in self._nodes or target_id not in self._nodes:
            return False
        
        if len(self._outgoing[source_id]) >= self.MAX_EDGES_PER_NODE:
            return False
        
        # Check for duplicate
        for e in self._outgoing[source_id]:
            if e.target_id == target_id and e.edge_type == edge_type:
                return False
        
        edge = CognitiveEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            weight=weight,
        )
        
        self._edges.append(edge)
        self._outgoing[source_id].append(edge)
        self._incoming[target_id].append(edge)
        
        return True
    
    def get_node(self, node_id: str) -> Optional[CognitiveNode]:
        """Get a node by ID."""
        return self._nodes.get(node_id)
    
    def get_nodes_by_type(self, node_type: CognitiveNodeType) -> list[CognitiveNode]:
        """Get all nodes of a given type."""
        return [n for n in self._nodes.values() if n.node_type == node_type]
    
    def get_outgoing_edges(self, node_id: str) -> list[CognitiveEdge]:
        """Get outgoing edges from a node."""
        return list(self._outgoing.get(node_id, []))
    
    def get_incoming_edges(self, node_id: str) -> list[CognitiveEdge]:
        """Get incoming edges to a node."""
        return list(self._incoming.get(node_id, []))
    
    def get_decision_points(self) -> list[CognitiveNode]:
        """Get all decision point nodes."""
        return self.get_nodes_by_type(CognitiveNodeType.DECISION_POINT)
    
    def get_invariants(self) -> list[CognitiveNode]:
        """Get all invariant nodes."""
        return self.get_nodes_by_type(CognitiveNodeType.INVARIANT)
    
    def count_branching(self, node_id: str) -> int:
        """
        Count branching factor from a node.
        
        Branching = number of BRANCHES edges.
        """
        branching = 0
        for edge in self._outgoing.get(node_id, []):
            if edge.edge_type == CognitiveEdgeType.BRANCHES:
                branching += 1
        return branching
    
    def compute_total_branching(self) -> int:
        """Compute total branching factor across all decision points."""
        total = 0
        for node in self.get_decision_points():
            total += self.count_branching(node.node_id)
        return total
    
    def find_paths_to_anchors(
        self,
        start_id: str,
        max_depth: int = 5,
    ) -> list[list[str]]:
        """
        Find all paths from start to explanation anchors (BFS).
        
        Respects MAX_DEPTH constraint.
        """
        max_depth = min(max_depth, self.MAX_DEPTH)
        
        if start_id not in self._nodes:
            return []
        
        paths = []
        queue = deque([(start_id, [start_id])])
        
        while queue:
            current, path = queue.popleft()
            
            if len(path) > max_depth + 1:
                continue
            
            # Check if we reached an anchor
            node = self._nodes.get(current)
            if node and node.is_anchor and len(path) > 1:
                paths.append(path)
                continue
            
            for edge in self._outgoing.get(current, []):
                if edge.target_id not in path:
                    queue.append((edge.target_id, path + [edge.target_id]))
        
        return paths
    
    def compute_path_complexity(self, path: list[str]) -> int:
        """
        Compute complexity of a path.
        
        Complexity = sum of decision points + branching factors.
        """
        complexity = 0
        for node_id in path:
            node = self._nodes.get(node_id)
            if node:
                if node.is_decision:
                    complexity += 1
                complexity += self.count_branching(node_id)
        return complexity
    
    def get_dependent_nodes(self, node_id: str) -> list[str]:
        """Get nodes that depend on the given node."""
        dependents = []
        for edge in self._incoming.get(node_id, []):
            if edge.edge_type == CognitiveEdgeType.DEPENDS_ON:
                dependents.append(edge.source_id)
        return dependents
    
    def get_constrained_nodes(self, invariant_id: str) -> list[str]:
        """Get nodes constrained by an invariant."""
        constrained = []
        for edge in self._outgoing.get(invariant_id, []):
            if edge.edge_type == CognitiveEdgeType.CONSTRAINS:
                constrained.append(edge.target_id)
        return constrained
    
    def iter_all_nodes(self) -> Iterator[CognitiveNode]:
        """Iterate over all nodes."""
        return iter(self._nodes.values())
    
    def iter_all_edges(self) -> Iterator[CognitiveEdge]:
        """Iterate over all edges."""
        return iter(self._edges)


__all__ = [
    "CognitiveNodeType",
    "CognitiveEdgeType",
    "CognitiveNode",
    "CognitiveEdge",
    "CognitiveGraph",
]
