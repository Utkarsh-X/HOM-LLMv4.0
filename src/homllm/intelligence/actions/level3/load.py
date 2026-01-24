"""
Level-3 Cognitive Load Regulator

Regulates cognitive load in reasoning paths.
Reorders exposure to reduce mental effort - never removes logic.

Allowed actions:
- LIMIT branching
- COLLAPSE equivalent paths
- LINEARIZE decisions
- PUSH complexity later
- ISOLATE deep logic

CONSTRAINTS (ABSOLUTE):
- Never removes logic
- Only reorders/reorganizes
- Deterministic
- No LLM or ML
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from homllm.intelligence.actions.level3.plan import (
    CognitiveAction,
    CognitiveActionType,
    ReasoningPath,
)
from homllm.intelligence.actions.level3.graph import (
    CognitiveGraph,
    CognitiveNodeType,
)

if TYPE_CHECKING:
    from homllm.intelligence.interfaces import DiagnosticSnapshot


class CognitiveLoadRegulator:
    """
    Regulates cognitive load by proposing shaping actions.
    
    Uses diagnostic signals:
    - Branching factor
    - Nesting depth
    - Symbol fan-out
    - Concept collision
    - State explosion risk
    
    Actions reorder exposure, never remove logic.
    """
    
    # Thresholds for cognitive load regulation
    BRANCHING_THRESHOLD = 2       # Max acceptable branching factor
    NESTING_THRESHOLD = 3         # Max acceptable nesting depth
    PATH_COMPLEXITY_THRESHOLD = 4 # Max acceptable path complexity
    HIGH_LOAD_THRESHOLD = 0.6     # Cognitive load score threshold
    
    def __init__(self):
        pass
    
    def regulate(
        self,
        graph: CognitiveGraph,
        paths: tuple[ReasoningPath, ...],
        diagnostics: DiagnosticSnapshot,
    ) -> list[CognitiveAction]:
        """
        Propose cognitive load regulation actions.
        
        Args:
            graph: Cognitive graph
            paths: Extracted reasoning paths
            diagnostics: For cognitive load metrics
            
        Returns:
            List of regulation actions
        """
        actions = []
        
        # 1. Analyze branching and propose LIMIT actions
        branching_actions = self._analyze_branching(graph)
        actions.extend(branching_actions)
        
        # 2. Analyze path complexity and propose ISOLATE actions
        complexity_actions = self._analyze_path_complexity(paths, graph)
        actions.extend(complexity_actions)
        
        # 3. Analyze cognitive load from diagnostics
        if diagnostics.level3.status == "available" and diagnostics.level3.result:
            load_actions = self._analyze_diagnostic_load(diagnostics.level3.result, graph)
            actions.extend(load_actions)
        
        # 4. Propose path linearization if needed
        linearization_actions = self._propose_linearization(paths)
        actions.extend(linearization_actions)
        
        return actions
    
    def _analyze_branching(self, graph: CognitiveGraph) -> list[CognitiveAction]:
        """Analyze branching and propose LIMIT actions."""
        actions = []
        
        decision_points = graph.get_decision_points()
        
        for node in decision_points:
            branching = graph.count_branching(node.node_id)
            
            if branching > self.BRANCHING_THRESHOLD:
                actions.append(CognitiveAction(
                    action_type=CognitiveActionType.LIMIT,
                    target=node.node_id,
                    parameters=(
                        ("current_branching", branching),
                        ("target_branching", self.BRANCHING_THRESHOLD),
                    ),
                    justification=f"Decision point has high branching factor ({branching} > {self.BRANCHING_THRESHOLD})",
                    diagnostic_source="cognitive_graph",
                ))
        
        return actions
    
    def _analyze_path_complexity(
        self,
        paths: tuple[ReasoningPath, ...],
        graph: CognitiveGraph,
    ) -> list[CognitiveAction]:
        """Analyze path complexity and propose ISOLATE actions."""
        actions = []
        
        for path in paths:
            if path.complexity > self.PATH_COMPLEXITY_THRESHOLD:
                # Find the most complex step in the path
                max_complexity_step = None
                max_complexity = 0
                
                for step in path.steps:
                    node = graph.get_node(step.step_id)
                    if node and node.complexity > max_complexity:
                        max_complexity = node.complexity
                        max_complexity_step = step
                
                if max_complexity_step:
                    actions.append(CognitiveAction(
                        action_type=CognitiveActionType.ISOLATE,
                        target=max_complexity_step.step_id,
                        parameters=(
                            ("path_complexity", path.complexity),
                            ("step_complexity", max_complexity),
                        ),
                        justification=f"Path complexity exceeds threshold ({path.complexity} > {self.PATH_COMPLEXITY_THRESHOLD})",
                        diagnostic_source="reasoning_paths",
                    ))
        
        return actions
    
    def _analyze_diagnostic_load(
        self,
        l3_result,
        graph: CognitiveGraph,
    ) -> list[CognitiveAction]:
        """Analyze cognitive load from Level-3 diagnostics."""
        actions = []
        
        if l3_result.cognitive_load is None:
            return actions
        
        cog_load = l3_result.cognitive_load
        
        # Check for high-load blocks
        for block_load in cog_load.block_loads:
            if block_load.load_score > self.HIGH_LOAD_THRESHOLD:
                # Find corresponding node in graph
                node_id = f"block:{block_load.block_id}"
                
                # Propose ISOLATE if nesting is high
                if block_load.nesting_score > 0.5:
                    actions.append(CognitiveAction(
                        action_type=CognitiveActionType.ISOLATE,
                        target=block_load.block_id,
                        parameters=(
                            ("load_score", block_load.load_score),
                            ("nesting_score", block_load.nesting_score),
                        ),
                        justification=f"High cognitive load ({block_load.load_score:.2f}) with deep nesting",
                        diagnostic_source="cognitive_load",
                    ))
                
                # Propose LIMIT if branching is high
                if block_load.branching_score > 0.5:
                    actions.append(CognitiveAction(
                        action_type=CognitiveActionType.LIMIT,
                        target=block_load.block_id,
                        parameters=(
                            ("load_score", block_load.load_score),
                            ("branching_score", block_load.branching_score),
                        ),
                        justification=f"High cognitive load ({block_load.load_score:.2f}) with high branching",
                        diagnostic_source="cognitive_load",
                    ))
        
        return actions
    
    def _propose_linearization(
        self,
        paths: tuple[ReasoningPath, ...],
    ) -> list[CognitiveAction]:
        """Propose path linearization for complex paths."""
        actions = []
        
        for path in paths:
            # Count decision points in path
            decision_count = sum(
                1 for step in path.steps if step.step_type == "decision"
            )
            
            if decision_count > 1:
                actions.append(CognitiveAction(
                    action_type=CognitiveActionType.ORDER,
                    target=path.path_id,
                    parameters=(
                        ("entry", path.entry_point),
                        ("exit", path.exit_point),
                        ("decisions", decision_count),
                    ),
                    justification=f"Linearize path with {decision_count} decision points",
                    diagnostic_source="reasoning_paths",
                ))
        
        return actions


__all__ = [
    "CognitiveLoadRegulator",
]
