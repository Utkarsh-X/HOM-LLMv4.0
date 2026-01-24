"""
Level-2 Gap and Redundancy Detection

Identifies semantic gaps (unsatisfied obligations) and
redundant blocks (candidates for collapse).

CONSTRAINTS (ABSOLUTE):
- Set coverage analysis only
- No inference or guessing
- No LLM or ML
- Deterministic
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from homllm.intelligence.actions.level2.plan import (
    SemanticObligation,
    SemanticGap,
)
from homllm.intelligence.actions.level2.graph import (
    SemanticGraph,
    NodeType,
    EdgeType,
)

if TYPE_CHECKING:
    from homllm.intelligence.interfaces import DiagnosticSnapshot


class GapDetector:
    """
    Detects semantic gaps from unsatisfied obligations.
    
    Uses the semantic graph to check coverage.
    Gaps are objective findings, not inferences.
    """
    
    def detect(
        self,
        obligations: tuple[SemanticObligation, ...],
        graph: SemanticGraph,
        diagnostics: DiagnosticSnapshot,
    ) -> tuple[SemanticGap, ...]:
        """
        Detect gaps by checking obligation satisfaction.
        
        Args:
            obligations: Obligations to check
            graph: Semantic graph with blocks and concepts
            diagnostics: For additional context
            
        Returns:
            Tuple of detected gaps
        """
        gaps: list[SemanticGap] = []
        
        for obligation in obligations:
            if obligation.is_satisfied:
                continue
            
            # Check concept coverage
            missing_concepts = self._find_missing_concepts(
                obligation.required_concepts,
                graph,
            )
            
            # Check role coverage
            missing_roles = self._find_missing_roles(
                obligation.required_roles,
                obligation.required_concepts,
                graph,
                diagnostics,
            )
            
            # If anything missing, it's a gap
            if missing_concepts or missing_roles:
                severity = self._compute_severity(
                    missing_concepts,
                    missing_roles,
                    obligation,
                )
                
                reason = self._build_reason(
                    obligation,
                    missing_concepts,
                    missing_roles,
                )
                
                gaps.append(SemanticGap(
                    obligation_name=obligation.name,
                    missing_concepts=tuple(missing_concepts),
                    missing_roles=tuple(missing_roles),
                    severity=severity,
                    reason=reason,
                ))
        
        return tuple(gaps)
    
    def _find_missing_concepts(
        self,
        required_concepts: tuple[str, ...],
        graph: SemanticGraph,
    ) -> list[str]:
        """Find concepts not present in graph."""
        missing = []
        
        for concept in required_concepts:
            # Check if concept node exists in graph
            concept_id = f"concept:{concept.lower()}"
            if graph.get_node(concept_id) is None:
                missing.append(concept)
        
        return missing
    
    def _find_missing_roles(
        self,
        required_roles: tuple[str, ...],
        required_concepts: tuple[str, ...],
        graph: SemanticGraph,
        diagnostics: DiagnosticSnapshot,
    ) -> list[str]:
        """Find roles not satisfied for required concepts."""
        missing = []
        
        # Map role names to edge types
        role_to_edge = {
            "DEFINE": EdgeType.DEFINES,
            "IMPLEMENT": EdgeType.IMPLEMENTS,
            "EXPLAIN": EdgeType.EXPLAINS,
        }
        
        for role in required_roles:
            edge_type = role_to_edge.get(role)
            if edge_type is None:
                continue
            
            # Check if any concept has this role covered
            role_satisfied = False
            
            for concept in required_concepts:
                concept_id = f"concept:{concept.lower()}"
                blocks = graph.get_blocks_for_concept(concept_id)
                
                if blocks.get(edge_type):
                    role_satisfied = True
                    break
            
            if not role_satisfied:
                missing.append(role)
        
        return missing
    
    def _compute_severity(
        self,
        missing_concepts: list[str],
        missing_roles: list[str],
        obligation: SemanticObligation,
    ) -> str:
        """Compute gap severity."""
        # Critical: concept completely missing
        if missing_concepts:
            return "critical"
        
        # Critical: required role from query intent
        if obligation.source == "query_intent" and missing_roles:
            return "critical"
        
        # Moderate: role gaps from coverage analysis
        if missing_roles:
            return "moderate"
        
        return "minor"
    
    def _build_reason(
        self,
        obligation: SemanticObligation,
        missing_concepts: list[str],
        missing_roles: list[str],
    ) -> str:
        """Build human-readable reason for gap."""
        parts = []
        
        if missing_concepts:
            parts.append(f"Concepts not covered: {', '.join(missing_concepts)}")
        
        if missing_roles:
            parts.append(f"Roles not satisfied: {', '.join(missing_roles)}")
        
        return "; ".join(parts) if parts else f"Obligation '{obligation.name}' not satisfied"


class RedundancyDetector:
    """
    Detects semantic redundancy for collapse candidates.
    
    Two blocks are redundant if:
    1. They satisfy the same obligation
    2. They cover the same concept with same role
    3. One has strictly lower signal ratio
    """
    
    def detect(
        self,
        graph: SemanticGraph,
        diagnostics: DiagnosticSnapshot,
    ) -> list[tuple[str, str, str]]:
        """
        Detect redundant block pairs.
        
        Returns:
            List of (block_a, block_b, reason) tuples where
            block_b is candidate for collapse into block_a.
        """
        redundancies = []
        
        # Get all concept nodes
        concept_nodes = graph.get_nodes_by_type(NodeType.CONCEPT)
        
        # Get block signal ratios from L1 diagnostics
        signal_ratios = self._get_signal_ratios(diagnostics)
        
        for concept_node in concept_nodes:
            concept_id = concept_node.node_id
            blocks_by_role = graph.get_blocks_for_concept(concept_id)
            
            # Check for redundancy within each role
            for edge_type, block_ids in blocks_by_role.items():
                if len(block_ids) < 2:
                    continue
                
                # Sort by signal ratio descending
                sorted_blocks = sorted(
                    block_ids,
                    key=lambda b: signal_ratios.get(b, 0.0),
                    reverse=True,
                )
                
                # First block is canonical, rest are redundant
                canonical = sorted_blocks[0]
                for redundant in sorted_blocks[1:]:
                    canonical_ratio = signal_ratios.get(canonical, 0.0)
                    redundant_ratio = signal_ratios.get(redundant, 0.0)
                    
                    if redundant_ratio < canonical_ratio:
                        reason = (
                            f"Both {edge_type.value} concept '{concept_node.label}'; "
                            f"'{redundant}' has lower signal ({redundant_ratio:.2f} vs {canonical_ratio:.2f})"
                        )
                        redundancies.append((canonical, redundant, reason))
        
        return redundancies
    
    def _get_signal_ratios(self, diagnostics: DiagnosticSnapshot) -> dict[str, float]:
        """Extract signal ratios from L1 diagnostics."""
        ratios = {}
        
        if diagnostics.level1.status != "available":
            return ratios
        
        for block in diagnostics.level1.blocks:
            ratios[block.block_id] = block.signal_ratio
        
        return ratios


__all__ = [
    "GapDetector",
    "RedundancyDetector",
]
