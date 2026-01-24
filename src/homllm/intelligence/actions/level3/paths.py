"""
Level-3 Reasoning Path Extractor

Extracts minimal necessary reasoning paths from the cognitive graph.
Paths connect query intent through semantic obligations to explanation anchors.

Rules:
- Start from query intent (entry nodes)
- Traverse through reasoning steps
- Stop at explanation anchors
- No speculative paths
- No branching expansion

CONSTRAINTS (ABSOLUTE):
- No loops or recursion in path finding
- No speculative path generation
- Deterministic
- Read-only
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from homllm.intelligence.actions.level3.plan import (
    ReasoningStep,
    ReasoningPath,
)
from homllm.intelligence.actions.level3.graph import (
    CognitiveGraph,
    CognitiveNodeType,
    CognitiveEdgeType,
)

if TYPE_CHECKING:
    from homllm.intelligence.interfaces import DiagnosticSnapshot


class ReasoningPathExtractor:
    """
    Extracts minimal reasoning paths from cognitive graph.
    
    A reasoning path is the minimal sequence of steps required
    for the LLM to reach understanding.
    
    Principles:
    - Start from query intent
    - Follow only necessary connections
    - Stop at explanation anchors
    - Collect invariants along the way
    """
    
    def __init__(self, max_paths: int = 5, max_path_length: int = 6):
        """
        Initialize extractor.
        
        Args:
            max_paths: Maximum number of paths to extract
            max_path_length: Maximum steps in a single path
        """
        self.max_paths = max_paths
        self.max_path_length = max_path_length
    
    def extract(
        self,
        graph: CognitiveGraph,
        diagnostics: DiagnosticSnapshot,
    ) -> tuple[ReasoningPath, ...]:
        """
        Extract reasoning paths from the cognitive graph.
        
        Args:
            graph: Cognitive graph to extract from
            diagnostics: For additional context
            
        Returns:
            Tuple of ReasoningPath objects
        """
        paths = []
        
        # Start from each entry point
        for entry_id in graph.entry_points[:3]:  # Limit entry points
            entry_paths = self._extract_from_entry(graph, entry_id)
            paths.extend(entry_paths)
            
            if len(paths) >= self.max_paths:
                break
        
        # Deduplicate and rank paths
        ranked_paths = self._rank_paths(paths)
        
        return tuple(ranked_paths[:self.max_paths])
    
    def _extract_from_entry(
        self,
        graph: CognitiveGraph,
        entry_id: str,
    ) -> list[ReasoningPath]:
        """Extract paths starting from a specific entry node."""
        paths = []
        
        # Find all paths to anchors
        raw_paths = graph.find_paths_to_anchors(entry_id, self.max_path_length)
        
        for i, raw_path in enumerate(raw_paths[:self.max_paths]):
            # Convert to ReasoningPath
            steps = self._build_steps(graph, raw_path)
            invariants = self._collect_invariants(graph, raw_path)
            complexity = graph.compute_path_complexity(raw_path)
            
            path = ReasoningPath(
                path_id=f"path_{entry_id}_{i}",
                steps=tuple(steps),
                invariants=tuple(invariants),
                entry_point=entry_id,
                exit_point=raw_path[-1] if raw_path else entry_id,
                complexity=complexity,
            )
            paths.append(path)
        
        return paths
    
    def _build_steps(
        self,
        graph: CognitiveGraph,
        raw_path: list[str],
    ) -> list[ReasoningStep]:
        """Build reasoning steps from node path."""
        steps = []
        
        for node_id in raw_path:
            node = graph.get_node(node_id)
            if node is None:
                continue
            
            # Determine step type from node type
            step_type = self._node_type_to_step_type(node.node_type)
            
            step = ReasoningStep(
                step_id=node_id,
                step_type=step_type,
                block_id=node.block_id,
                description=node.label,
            )
            steps.append(step)
        
        return steps
    
    def _node_type_to_step_type(self, node_type: CognitiveNodeType) -> str:
        """Map node type to step type."""
        mapping = {
            CognitiveNodeType.REASONING_STEP: "step",
            CognitiveNodeType.DECISION_POINT: "decision",
            CognitiveNodeType.INVARIANT: "constraint",
            CognitiveNodeType.ASSUMPTION: "assumption",
            CognitiveNodeType.EXPLANATION_ANCHOR: "anchor",
            CognitiveNodeType.STATE_TRANSITION: "transition",
        }
        return mapping.get(node_type, "step")
    
    def _collect_invariants(
        self,
        graph: CognitiveGraph,
        raw_path: list[str],
    ) -> list[str]:
        """Collect invariants that affect the path."""
        invariants = []
        
        # Get all invariant nodes
        all_invariants = graph.get_invariants()
        
        for inv_node in all_invariants:
            # Check if invariant constrains any node in the path
            constrained = graph.get_constrained_nodes(inv_node.node_id)
            if any(node_id in raw_path for node_id in constrained):
                invariants.append(inv_node.node_id)
        
        return invariants
    
    def _rank_paths(self, paths: list[ReasoningPath]) -> list[ReasoningPath]:
        """Rank paths by quality (lower complexity is better)."""
        # Sort by complexity (ascending), then by path length (ascending)
        return sorted(
            paths,
            key=lambda p: (p.complexity, len(p.steps)),
        )


__all__ = [
    "ReasoningPathExtractor",
]
