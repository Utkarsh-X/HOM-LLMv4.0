"""
Level-2 Semantic Action Intelligence Engine

Main orchestrator that:
1. Builds semantic graph from diagnostics
2. Extracts semantic obligations
3. Detects gaps and redundancies
4. Produces ordered SemanticActionPlan

CONSTRAINTS (ABSOLUTE):
- Deterministic: same input → same output
- No LLM or ML
- No context mutation
- No learning or memory
- Can be safely disabled
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homllm.intelligence.actions.level2.plan import (
    SemanticAction,
    SemanticActionType,
    SemanticActionPlan,
    SemanticObligation,
    SemanticGap,
    SEMANTIC_ACTION_ORDER,
)
from homllm.intelligence.actions.level2.graph import (
    SemanticGraph,
    NodeType,
    EdgeType,
)
from homllm.intelligence.actions.level2.obligations import ObligationAnalyzer
from homllm.intelligence.actions.level2.gaps import GapDetector, RedundancyDetector

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact
    from homllm.intelligence.interfaces import DiagnosticSnapshot


class SemanticActionEngine:
    """
    Level-2 Semantic Action Intelligence Engine.
    
    Answers: "Does the context contain the semantic information 
              required to be understood?"
    
    This is semantic constraint satisfaction, not reasoning.
    
    Pipeline:
        Diagnostics → Graph Builder → Obligation Analyzer 
                    → Gap Detection → Redundancy Detection 
                    → Action Planner → SemanticActionPlan
    
    Usage:
        engine = SemanticActionEngine(enabled=True)
        plan = engine.propose(diagnostics, context)
    """
    
    def __init__(self, enabled: bool = True):
        """
        Initialize the engine.
        
        Args:
            enabled: If False, propose() returns empty plan.
        """
        self.enabled = enabled
        self._obligation_analyzer = ObligationAnalyzer()
        self._gap_detector = GapDetector()
        self._redundancy_detector = RedundancyDetector()
    
    def propose(
        self,
        diagnostics: DiagnosticSnapshot,
        context: ContextArtifact,
    ) -> SemanticActionPlan:
        """
        Propose semantic actions based on diagnostics.
        
        This is the ONLY entry point for the engine.
        Does NOT modify context, only proposes actions.
        
        Args:
            diagnostics: DiagnosticSnapshot
            context: ContextArtifact (read-only)
            
        Returns:
            SemanticActionPlan with ordered actions
        """
        if not self.enabled:
            return SemanticActionPlan.empty()
        
        # Need at least L2 or L3 diagnostics
        has_l2 = diagnostics.level2.status == "available"
        has_l3 = diagnostics.level3.status == "available"
        
        if not has_l2 and not has_l3:
            return SemanticActionPlan.empty()
        
        # Phase 1: Build semantic graph
        graph = self._build_semantic_graph(diagnostics)
        
        # Phase 2: Extract obligations
        obligations = self._obligation_analyzer.analyze(diagnostics)
        
        # Phase 3: Check obligation satisfaction and detect gaps
        satisfied_obligations = self._check_satisfaction(obligations, graph, diagnostics)
        gaps = self._gap_detector.detect(obligations, graph, diagnostics)
        
        # Phase 4: Detect redundancies
        redundancies = self._redundancy_detector.detect(graph, diagnostics)
        
        # Phase 5: Generate actions
        actions = self._generate_actions(
            gaps,
            redundancies,
            graph,
            diagnostics,
        )
        
        # Phase 6: Order actions
        ordered_actions = self._order_actions(actions)
        
        # Build explanations
        explanations = self._build_explanations(
            obligations,
            satisfied_obligations,
            gaps,
            redundancies,
        )
        
        return SemanticActionPlan(
            actions=ordered_actions,
            obligations=obligations,
            gaps=gaps,
            explanations=tuple(explanations),
            total_obligations=len(obligations),
            satisfied_obligations=satisfied_obligations,
            total_gaps=len(gaps),
            critical_gaps=sum(1 for g in gaps if g.severity == "critical"),
        )
    
    def _build_semantic_graph(self, diagnostics: DiagnosticSnapshot) -> SemanticGraph:
        """Build semantic graph from diagnostics."""
        graph = SemanticGraph()
        
        # Add block nodes from L1
        if diagnostics.level1.status == "available":
            for block in diagnostics.level1.blocks:
                graph.add_node(
                    node_id=block.block_id,
                    node_type=NodeType.BLOCK,
                    label=block.symbol or block.block_id,
                    metadata={"file": block.file, "tokens": block.tokens},
                )
        
        # Add concept nodes and edges from L3
        if diagnostics.level3.status == "available" and diagnostics.level3.result:
            l3 = diagnostics.level3.result
            
            # Add concepts from query intent
            if l3.intent:
                for concept in l3.intent.concepts:
                    concept_id = f"concept:{concept.lower()}"
                    graph.add_node(
                        node_id=concept_id,
                        node_type=NodeType.CONCEPT,
                        label=concept,
                    )
            
            # Add edges based on block roles
            if l3.block_roles:
                self._add_role_edges(graph, l3.block_roles, l3.concept_gaps)
        
        return graph
    
    def _add_role_edges(self, graph: SemanticGraph, block_roles, concept_gaps):
        """Add edges from blocks to concepts based on roles."""
        from homllm.intelligence.diagnostics.context_level3.inspect_explanatory_roles import ExplanatoryRole
        
        # Map roles to edge types
        role_to_edge = {
            ExplanatoryRole.DEFINE: EdgeType.DEFINES,
            ExplanatoryRole.IMPLEMENT: EdgeType.IMPLEMENTS,
            ExplanatoryRole.EXPLAIN: EdgeType.EXPLAINS,
            ExplanatoryRole.SUPPORT: EdgeType.SUPPORTS,
        }
        
        # Get concept coverage if available
        coverage_map = {}
        if concept_gaps:
            for cov in concept_gaps.concept_coverage:
                coverage_map[cov.concept.lower()] = {
                    "define_blocks": cov.define_blocks,
                    "implement_blocks": cov.implement_blocks,
                    "explain_blocks": cov.explain_blocks,
                }
        
        # Create edges from coverage map
        for concept, coverage in coverage_map.items():
            concept_id = f"concept:{concept}"
            
            # Ensure concept node exists
            graph.add_node(concept_id, NodeType.CONCEPT, concept)
            
            for block_id in coverage.get("define_blocks", []):
                if graph.get_node(block_id):
                    graph.add_edge(block_id, concept_id, EdgeType.DEFINES)
            
            for block_id in coverage.get("implement_blocks", []):
                if graph.get_node(block_id):
                    graph.add_edge(block_id, concept_id, EdgeType.IMPLEMENTS)
            
            for block_id in coverage.get("explain_blocks", []):
                if graph.get_node(block_id):
                    graph.add_edge(block_id, concept_id, EdgeType.EXPLAINS)
    
    def _check_satisfaction(
        self,
        obligations: tuple[SemanticObligation, ...],
        graph: SemanticGraph,
        diagnostics: DiagnosticSnapshot,
    ) -> int:
        """Count how many obligations are satisfied."""
        satisfied = 0
        
        for obligation in obligations:
            # Check if all required concepts exist
            concepts_covered = all(
                graph.get_node(f"concept:{c.lower()}") is not None
                for c in obligation.required_concepts
            )
            
            # Check if all required roles are covered
            roles_covered = self._check_roles_covered(
                obligation.required_concepts,
                obligation.required_roles,
                graph,
            )
            
            if concepts_covered and roles_covered:
                satisfied += 1
        
        return satisfied
    
    def _check_roles_covered(
        self,
        concepts: tuple[str, ...],
        roles: tuple[str, ...],
        graph: SemanticGraph,
    ) -> bool:
        """Check if all roles are covered for concepts."""
        role_to_edge = {
            "DEFINE": EdgeType.DEFINES,
            "IMPLEMENT": EdgeType.IMPLEMENTS,
            "EXPLAIN": EdgeType.EXPLAINS,
        }
        
        for role in roles:
            edge_type = role_to_edge.get(role)
            if edge_type is None:
                continue
            
            role_found = False
            for concept in concepts:
                concept_id = f"concept:{concept.lower()}"
                blocks = graph.get_blocks_for_concept(concept_id)
                if blocks.get(edge_type):
                    role_found = True
                    break
            
            if not role_found:
                return False
        
        return True
    
    def _generate_actions(
        self,
        gaps: tuple[SemanticGap, ...],
        redundancies: list[tuple[str, str, str]],
        graph: SemanticGraph,
        diagnostics: DiagnosticSnapshot,
    ) -> list[SemanticAction]:
        """Generate semantic actions from gaps and redundancies."""
        actions = []
        
        # REQUIRE actions from gaps with missing concepts
        for gap in gaps:
            if gap.missing_concepts:
                for concept in gap.missing_concepts:
                    actions.append(SemanticAction(
                        action_type=SemanticActionType.REQUIRE,
                        target=concept,
                        justification=f"Concept '{concept}' required but not in context",
                        obligation_ref=gap.obligation_name,
                        diagnostic_source="concept_gaps",
                    ))
        
        # ENSURE actions from gaps with missing roles
        for gap in gaps:
            if gap.missing_roles:
                for role in gap.missing_roles:
                    actions.append(SemanticAction(
                        action_type=SemanticActionType.ENSURE,
                        target=role,
                        justification=f"Role '{role}' required for obligation '{gap.obligation_name}'",
                        obligation_ref=gap.obligation_name,
                        diagnostic_source="concept_gaps",
                    ))
        
        # COLLAPSE actions from redundancies
        for canonical, redundant, reason in redundancies:
            actions.append(SemanticAction(
                action_type=SemanticActionType.COLLAPSE,
                target=f"{redundant}->{canonical}",
                justification=reason,
                diagnostic_source="redundancy_detection",
            ))
        
        # PROMOTE actions for blocks that satisfy critical obligations
        actions.extend(self._generate_promote_actions(gaps, graph, diagnostics))
        
        # DEPRIORITIZE actions for low-signal blocks
        actions.extend(self._generate_deprioritize_actions(graph, diagnostics))
        
        return actions
    
    def _generate_promote_actions(
        self,
        gaps: tuple[SemanticGap, ...],
        graph: SemanticGraph,
        diagnostics: DiagnosticSnapshot,
    ) -> list[SemanticAction]:
        """Generate PROMOTE actions for blocks covering critical concepts."""
        actions = []
        
        # Get high-signal blocks from L1
        if diagnostics.level1.status != "available":
            return actions
        
        high_signal_blocks = [
            b for b in diagnostics.level1.blocks
            if b.signal_ratio > 0.6
        ]
        
        # Promote blocks that define or explain concepts
        for block in high_signal_blocks:
            outgoing = graph.get_outgoing_edges(block.block_id)
            
            for edge in outgoing:
                if edge.edge_type in (EdgeType.DEFINES, EdgeType.EXPLAINS):
                    actions.append(SemanticAction(
                        action_type=SemanticActionType.PROMOTE,
                        target=block.block_id,
                        justification=f"High signal ({block.signal_ratio:.2f}) block that {edge.edge_type.value} concepts",
                        diagnostic_source="structural_diagnostics",
                    ))
                    break  # One promote per block
        
        return actions
    
    def _generate_deprioritize_actions(
        self,
        graph: SemanticGraph,
        diagnostics: DiagnosticSnapshot,
    ) -> list[SemanticAction]:
        """Generate DEPRIORITIZE actions for low-value blocks."""
        actions = []
        
        if diagnostics.level1.status != "available":
            return actions
        
        for block in diagnostics.level1.blocks:
            # Low signal and no semantic connections
            outgoing = graph.get_outgoing_edges(block.block_id)
            
            if block.signal_ratio < 0.3 and len(outgoing) == 0:
                actions.append(SemanticAction(
                    action_type=SemanticActionType.DEPRIORITIZE,
                    target=block.block_id,
                    justification=f"Low signal ({block.signal_ratio:.2f}) with no semantic connections",
                    diagnostic_source="structural_diagnostics",
                ))
        
        return actions
    
    def _order_actions(self, actions: list[SemanticAction]) -> tuple[SemanticAction, ...]:
        """Order actions by priority."""
        type_priority = {t: i for i, t in enumerate(SEMANTIC_ACTION_ORDER)}
        
        sorted_actions = sorted(
            actions,
            key=lambda a: (
                type_priority.get(a.action_type, 99),
                a.target,  # Stable secondary sort
            )
        )
        
        return tuple(sorted_actions)
    
    def _build_explanations(
        self,
        obligations: tuple[SemanticObligation, ...],
        satisfied: int,
        gaps: tuple[SemanticGap, ...],
        redundancies: list[tuple[str, str, str]],
    ) -> list[str]:
        """Build human-readable explanations."""
        explanations = []
        
        total = len(obligations)
        if total > 0:
            coverage = (satisfied / total) * 100
            explanations.append(f"Obligation coverage: {satisfied}/{total} ({coverage:.0f}%)")
        
        if gaps:
            critical = sum(1 for g in gaps if g.severity == "critical")
            explanations.append(f"Detected {len(gaps)} gaps ({critical} critical)")
        
        if redundancies:
            explanations.append(f"Detected {len(redundancies)} semantic redundancies")
        
        return explanations


def create_semantic_engine(enabled: bool = True) -> SemanticActionEngine:
    """Factory function for dependency injection."""
    return SemanticActionEngine(enabled=enabled)


__all__ = [
    "SemanticActionEngine",
    "create_semantic_engine",
]
