"""
Level-2 Semantic Graph

Sparse directed graph for semantic relationship analysis.
Uses typed nodes and edges to model semantic structure.

CONSTRAINTS (ABSOLUTE):
- ≤200 nodes per query
- ≤5 edges per node
- Max traversal depth: 2
- In-memory only (no DB)
- No LLM or ML
- Deterministic
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Iterator


class NodeType(Enum):
    """Types of nodes in the semantic graph."""
    
    CONCEPT = "concept"           # Semantic concept from query/blocks
    BLOCK = "block"               # Context block by ID
    RESPONSIBILITY = "responsibility"  # Semantic obligation/role


class EdgeType(Enum):
    """Types of edges in the semantic graph."""
    
    DEFINES = "defines"       # Block defines concept
    IMPLEMENTS = "implements" # Block implements concept
    EXPLAINS = "explains"     # Block explains concept
    SUPPORTS = "supports"     # Block supports another block
    SATISFIES = "satisfies"   # Block satisfies obligation/responsibility


@dataclass(frozen=True)
class GraphNode:
    """
    A node in the semantic graph.
    
    Immutable for determinism.
    """
    
    node_id: str
    node_type: NodeType
    label: str  # Human-readable label
    metadata: tuple[tuple[str, Any], ...] = ()  # Frozen dict alternative
    
    @property
    def meta_dict(self) -> dict[str, Any]:
        """Convert metadata to dict."""
        return dict(self.metadata)


@dataclass(frozen=True)
class GraphEdge:
    """
    An edge in the semantic graph.
    
    Directed: source → target
    """
    
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0  # Edge strength (0.0 - 1.0)


class SemanticGraph:
    """
    Sparse directed semantic graph.
    
    Models semantic relationships between concepts, blocks, and obligations.
    
    Constraints enforced:
    - Max 200 nodes
    - Max 5 edges per node
    - Max traversal depth 2
    
    Usage:
        graph = SemanticGraph()
        graph.add_node("optimizer", NodeType.CONCEPT, "Optimizer")
        graph.add_node("block_1", NodeType.BLOCK, "resolve_conflicts")
        graph.add_edge("block_1", "optimizer", EdgeType.IMPLEMENTS)
    """
    
    MAX_NODES = 200
    MAX_EDGES_PER_NODE = 5
    MAX_DEPTH = 2
    
    def __init__(self):
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._outgoing: dict[str, list[GraphEdge]] = {}
        self._incoming: dict[str, list[GraphEdge]] = {}
    
    @property
    def node_count(self) -> int:
        """Number of nodes in graph."""
        return len(self._nodes)
    
    @property
    def edge_count(self) -> int:
        """Number of edges in graph."""
        return len(self._edges)
    
    def add_node(
        self,
        node_id: str,
        node_type: NodeType,
        label: str,
        metadata: Optional[dict[str, Any]] = None
    ) -> bool:
        """
        Add a node to the graph.
        
        Returns False if max nodes exceeded or node already exists.
        """
        if node_id in self._nodes:
            return False  # Already exists
        
        if len(self._nodes) >= self.MAX_NODES:
            return False  # Limit exceeded
        
        meta_tuple = tuple(sorted(metadata.items())) if metadata else ()
        node = GraphNode(
            node_id=node_id,
            node_type=node_type,
            label=label,
            metadata=meta_tuple,
        )
        self._nodes[node_id] = node
        self._outgoing[node_id] = []
        self._incoming[node_id] = []
        return True
    
    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType,
        weight: float = 1.0
    ) -> bool:
        """
        Add an edge to the graph.
        
        Returns False if:
        - Source or target node doesn't exist
        - Max edges per node exceeded
        - Edge already exists
        """
        if source_id not in self._nodes or target_id not in self._nodes:
            return False
        
        # Check edge limit per node
        if len(self._outgoing[source_id]) >= self.MAX_EDGES_PER_NODE:
            return False
        
        # Check for duplicate
        for e in self._outgoing[source_id]:
            if e.target_id == target_id and e.edge_type == edge_type:
                return False
        
        edge = GraphEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            weight=weight,
        )
        self._edges.append(edge)
        self._outgoing[source_id].append(edge)
        self._incoming[target_id].append(edge)
        return True
    
    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Get a node by ID."""
        return self._nodes.get(node_id)
    
    def get_nodes_by_type(self, node_type: NodeType) -> list[GraphNode]:
        """Get all nodes of a given type."""
        return [n for n in self._nodes.values() if n.node_type == node_type]
    
    def get_outgoing_edges(self, node_id: str) -> list[GraphEdge]:
        """Get all outgoing edges from a node."""
        return list(self._outgoing.get(node_id, []))
    
    def get_incoming_edges(self, node_id: str) -> list[GraphEdge]:
        """Get all incoming edges to a node."""
        return list(self._incoming.get(node_id, []))
    
    def get_neighbors(
        self,
        node_id: str,
        edge_type: Optional[EdgeType] = None,
        direction: str = "outgoing"
    ) -> list[str]:
        """
        Get neighboring node IDs.
        
        Args:
            node_id: Source node
            edge_type: Filter by edge type (None = all)
            direction: "outgoing", "incoming", or "both"
        """
        neighbors = []
        
        if direction in ("outgoing", "both"):
            for edge in self._outgoing.get(node_id, []):
                if edge_type is None or edge.edge_type == edge_type:
                    neighbors.append(edge.target_id)
        
        if direction in ("incoming", "both"):
            for edge in self._incoming.get(node_id, []):
                if edge_type is None or edge.edge_type == edge_type:
                    neighbors.append(edge.source_id)
        
        return neighbors
    
    def find_paths(
        self,
        start_id: str,
        end_id: str,
        max_depth: int = 2
    ) -> list[list[str]]:
        """
        Find all paths between two nodes (BFS, depth limited).
        
        Respects MAX_DEPTH constraint.
        """
        max_depth = min(max_depth, self.MAX_DEPTH)
        
        if start_id not in self._nodes or end_id not in self._nodes:
            return []
        
        paths = []
        queue = [(start_id, [start_id])]
        
        while queue:
            current, path = queue.pop(0)
            
            if len(path) > max_depth + 1:
                continue
            
            if current == end_id and len(path) > 1:
                paths.append(path)
                continue
            
            for edge in self._outgoing.get(current, []):
                if edge.target_id not in path:
                    queue.append((edge.target_id, path + [edge.target_id]))
        
        return paths
    
    def get_blocks_for_concept(self, concept_id: str) -> dict[EdgeType, list[str]]:
        """
        Get all blocks related to a concept, grouped by relationship.
        
        Returns dict mapping EdgeType -> list of block_ids.
        """
        result: dict[EdgeType, list[str]] = {
            EdgeType.DEFINES: [],
            EdgeType.IMPLEMENTS: [],
            EdgeType.EXPLAINS: [],
        }
        
        for edge in self._incoming.get(concept_id, []):
            if edge.edge_type in result:
                source_node = self._nodes.get(edge.source_id)
                if source_node and source_node.node_type == NodeType.BLOCK:
                    result[edge.edge_type].append(edge.source_id)
        
        return result
    
    def iter_all_nodes(self) -> Iterator[GraphNode]:
        """Iterate over all nodes."""
        return iter(self._nodes.values())
    
    def iter_all_edges(self) -> Iterator[GraphEdge]:
        """Iterate over all edges."""
        return iter(self._edges)


__all__ = [
    "NodeType",
    "EdgeType",
    "GraphNode",
    "GraphEdge",
    "SemanticGraph",
]
