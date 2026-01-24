"""
Level-3 Invariant and Ambiguity Controller

Protects invariants and isolates ambiguous regions.

Invariants:
- Precedence rules
- Ordering constraints
- Safety guarantees

Ambiguity sources:
- Mixed responsibilities
- Conflicting abstractions
- Similar identifiers
- Overlapping explanations

CONSTRAINTS (ABSOLUTE):
- Never removes logic
- Deterministic
- No LLM or ML
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from homllm.intelligence.actions.level3.plan import (
    CognitiveAction,
    CognitiveActionType,
    InvariantProtection,
    AmbiguityIsolation,
    ReasoningPath,
)
from homllm.intelligence.actions.level3.graph import (
    CognitiveGraph,
    CognitiveNodeType,
    CognitiveEdgeType,
)

if TYPE_CHECKING:
    from homllm.intelligence.interfaces import DiagnosticSnapshot


class InvariantController:
    """
    Protects invariants and isolates ambiguous regions.
    
    Invariants are constraints that must hold throughout reasoning.
    Ambiguities are regions that may confuse the LLM.
    """
    
    def __init__(self):
        pass
    
    def analyze(
        self,
        graph: CognitiveGraph,
        paths: tuple[ReasoningPath, ...],
        diagnostics: DiagnosticSnapshot,
    ) -> tuple[
        tuple[InvariantProtection, ...],
        tuple[AmbiguityIsolation, ...],
        list[CognitiveAction],
    ]:
        """
        Analyze invariants and ambiguities.
        
        Args:
            graph: Cognitive graph
            paths: Reasoning paths
            diagnostics: For additional context
            
        Returns:
            Tuple of (invariants, ambiguities, actions)
        """
        # 1. Extract invariants from graph and diagnostics
        invariants = self._extract_invariants(graph, paths, diagnostics)
        
        # 2. Detect ambiguities
        ambiguities = self._detect_ambiguities(graph, paths, diagnostics)
        
        # 3. Generate protection actions
        actions = self._generate_actions(invariants, ambiguities, graph)
        
        return invariants, ambiguities, actions
    
    def _extract_invariants(
        self,
        graph: CognitiveGraph,
        paths: tuple[ReasoningPath, ...],
        diagnostics: DiagnosticSnapshot,
    ) -> tuple[InvariantProtection, ...]:
        """Extract invariants from graph and diagnostics."""
        invariants = []
        
        # 1. Get invariants from graph nodes
        for node in graph.get_invariants():
            constrained = graph.get_constrained_nodes(node.node_id)
            
            invariants.append(InvariantProtection(
                invariant_id=node.node_id,
                invariant_type="constraint",
                description=node.label,
                protected_blocks=tuple(constrained),
                source="cognitive_graph",
            ))
        
        # 2. Extract ordering invariants from paths
        for path in paths:
            if len(path.steps) >= 2:
                # The order of steps is an invariant
                step_order = [s.step_id for s in path.steps]
                
                invariants.append(InvariantProtection(
                    invariant_id=f"order_{path.path_id}",
                    invariant_type="ordering",
                    description=f"Reasoning order: {' → '.join(step_order[:3])}...",
                    protected_blocks=tuple(
                        s.block_id for s in path.steps if s.block_id
                    ),
                    source="reasoning_paths",
                ))
        
        # 3. Extract invariants from L3 diagnostics
        if diagnostics.level3.status == "available" and diagnostics.level3.result:
            l3 = diagnostics.level3.result
            
            # Role balance can be an invariant
            if l3.explanatory_balance and l3.explanatory_balance.is_balanced:
                invariants.append(InvariantProtection(
                    invariant_id="role_balance",
                    invariant_type="balance",
                    description="Maintain explanatory role balance",
                    protected_blocks=(),
                    source="alignment_summary",
                ))
        
        return tuple(invariants[:10])  # Limit to 10 invariants
    
    def _detect_ambiguities(
        self,
        graph: CognitiveGraph,
        paths: tuple[ReasoningPath, ...],
        diagnostics: DiagnosticSnapshot,
    ) -> tuple[AmbiguityIsolation, ...]:
        """Detect ambiguous regions."""
        ambiguities = []
        
        # 1. Detect overlapping paths (same blocks in multiple paths)
        block_to_paths: dict[str, list[str]] = {}
        for path in paths:
            for step in path.steps:
                if step.block_id:
                    if step.block_id not in block_to_paths:
                        block_to_paths[step.block_id] = []
                    block_to_paths[step.block_id].append(path.path_id)
        
        for block_id, path_ids in block_to_paths.items():
            if len(path_ids) > 1:
                ambiguities.append(AmbiguityIsolation(
                    isolation_id=f"overlap_{block_id}",
                    ambiguity_type="overlap",
                    affected_blocks=(block_id,),
                    reason=f"Block appears in {len(path_ids)} different reasoning paths",
                ))
        
        # 2. Detect mixed responsibilities from L3
        if diagnostics.level3.status == "available" and diagnostics.level3.result:
            l3 = diagnostics.level3.result
            
            # Check for blocks with multiple roles
            for role in l3.block_roles:
                if role.secondary_role is not None:
                    ambiguities.append(AmbiguityIsolation(
                        isolation_id=f"mixed_{role.block_id}",
                        ambiguity_type="mixed_responsibility",
                        affected_blocks=(role.block_id,),
                        reason=f"Block has both {role.primary_role.value} and {role.secondary_role.value} roles",
                    ))
        
        # 3. Detect branching ambiguity (multiple branches from decision)
        for node in graph.get_decision_points():
            branching = graph.count_branching(node.node_id)
            if branching > 2:
                affected = [
                    edge.target_id 
                    for edge in graph.get_outgoing_edges(node.node_id)
                    if edge.edge_type == CognitiveEdgeType.BRANCHES
                ]
                
                ambiguities.append(AmbiguityIsolation(
                    isolation_id=f"branching_{node.node_id}",
                    ambiguity_type="high_branching",
                    affected_blocks=tuple(affected),
                    reason=f"Decision point branches to {branching} alternatives",
                ))
        
        return tuple(ambiguities[:10])  # Limit to 10 ambiguities
    
    def _generate_actions(
        self,
        invariants: tuple[InvariantProtection, ...],
        ambiguities: tuple[AmbiguityIsolation, ...],
        graph: CognitiveGraph,
    ) -> list[CognitiveAction]:
        """Generate protection and isolation actions."""
        actions = []
        
        # 1. PRESERVE actions for invariants
        for inv in invariants:
            if inv.invariant_type == "ordering":
                actions.append(CognitiveAction(
                    action_type=CognitiveActionType.ORDER,
                    target=inv.invariant_id,
                    parameters=(
                        ("protected_blocks", inv.protected_blocks),
                    ),
                    justification=inv.description,
                    diagnostic_source=inv.source,
                ))
            else:
                actions.append(CognitiveAction(
                    action_type=CognitiveActionType.PRESERVE,
                    target=inv.invariant_id,
                    parameters=(
                        ("type", inv.invariant_type),
                        ("protected_blocks", inv.protected_blocks),
                    ),
                    justification=inv.description,
                    diagnostic_source=inv.source,
                ))
        
        # 2. ISOLATE/SEPARATE actions for ambiguities
        for amb in ambiguities:
            if amb.ambiguity_type == "mixed_responsibility":
                actions.append(CognitiveAction(
                    action_type=CognitiveActionType.SEPARATE,
                    target=amb.affected_blocks[0] if amb.affected_blocks else amb.isolation_id,
                    parameters=(
                        ("ambiguity_type", amb.ambiguity_type),
                    ),
                    justification=amb.reason,
                    diagnostic_source="invariant_controller",
                ))
            else:
                actions.append(CognitiveAction(
                    action_type=CognitiveActionType.ISOLATE,
                    target=amb.isolation_id,
                    parameters=(
                        ("ambiguity_type", amb.ambiguity_type),
                        ("affected_blocks", amb.affected_blocks),
                    ),
                    justification=amb.reason,
                    diagnostic_source="invariant_controller",
                ))
        
        # 3. ANCHOR actions for explanation anchors
        for anchor_id in graph.anchors:
            node = graph.get_node(anchor_id)
            if node:
                actions.append(CognitiveAction(
                    action_type=CognitiveActionType.ANCHOR,
                    target=anchor_id,
                    parameters=(
                        ("block_id", node.block_id),
                    ),
                    justification=f"Establish explanation anchor: {node.label}",
                    diagnostic_source="cognitive_graph",
                ))
        
        return actions


__all__ = [
    "InvariantController",
]
