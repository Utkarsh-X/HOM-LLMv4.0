"""
Level-3 Cognitive Action Intelligence Engine

Main orchestrator that shapes reasoning topology for LLM comprehension.
This is a reasoning compiler, NOT an agent.

Pipeline:
    Diagnostics → Cognitive Graph Builder → Reasoning Path Extractor
                → Cognitive Load Regulator → Invariant Controller
                → Cognitive Action Planner → CognitiveActionPlan

Goal: Make correct reasoning structurally unavoidable for the LLM.

CONSTRAINTS (ABSOLUTE):
- Deterministic: same input → same output
- Non-recursive: no loops
- Non-autonomous: no agent behavior
- Non-learning: no memory or adaptation
- Zero LLM calls
- Auditable: every action has justification
- Disableable via config
- Low latency
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homllm.intelligence.actions.level3.plan import (
    CognitiveAction,
    CognitiveActionType,
    CognitiveActionPlan,
    ReasoningPath,
)
from homllm.intelligence.actions.level3.graph import (
    CognitiveGraph,
    CognitiveNodeType,
    CognitiveEdgeType,
)
from homllm.intelligence.actions.level3.paths import ReasoningPathExtractor
from homllm.intelligence.actions.level3.load import CognitiveLoadRegulator
from homllm.intelligence.actions.level3.invariants import InvariantController
from homllm.intelligence.actions.level3.planner import CognitiveActionPlanner

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact
    from homllm.intelligence.interfaces import DiagnosticSnapshot


class Level3ActionEngine:
    """
    Level-3 Cognitive Action Intelligence Engine.
    
    Shapes reasoning topology so the LLM reasons correctly by default.
    This is a reasoning compiler, NOT an agent.
    
    Usage:
        engine = Level3ActionEngine(enabled=True)
        plan = engine.propose(diagnostics, context)
        
        # Plan contains shaping actions, not mutations
        for action in plan.actions:
            print(f"{action.type_name}: {action.target}")
    """
    
    def __init__(self, enabled: bool = True):
        """
        Initialize the engine.
        
        Args:
            enabled: If False, propose() returns empty plan.
        """
        self.enabled = enabled
        self._path_extractor = ReasoningPathExtractor()
        self._load_regulator = CognitiveLoadRegulator()
        self._invariant_controller = InvariantController()
        self._planner = CognitiveActionPlanner()
    
    def propose(
        self,
        diagnostics: DiagnosticSnapshot,
        context: ContextArtifact,
    ) -> CognitiveActionPlan:
        """
        Propose cognitive shaping actions.
        
        This is the ONLY entry point for the engine.
        Does NOT modify context, only proposes shaping actions.
        
        Args:
            diagnostics: DiagnosticSnapshot
            context: ContextArtifact (read-only)
            
        Returns:
            CognitiveActionPlan with ordered shaping actions
        """
        if not self.enabled:
            return CognitiveActionPlan.empty()
        
        # Need at least L1 diagnostics for block info
        if diagnostics.level1.status != "available":
            return CognitiveActionPlan.empty()
        
        # Phase 1: Build cognitive graph
        graph = self._build_cognitive_graph(diagnostics)
        
        if graph.node_count == 0:
            return CognitiveActionPlan.empty()
        
        # Phase 2: Extract reasoning paths
        paths = self._path_extractor.extract(graph, diagnostics)
        
        # Phase 3: Regulate cognitive load
        load_actions = self._load_regulator.regulate(graph, paths, diagnostics)
        
        # Phase 4: Protect invariants and isolate ambiguities
        invariants, ambiguities, inv_actions = self._invariant_controller.analyze(
            graph, paths, diagnostics
        )
        
        # Phase 5: Final planning
        plan = self._planner.plan(
            load_actions=load_actions,
            invariant_actions=inv_actions,
            paths=paths,
            invariants=invariants,
            ambiguities=ambiguities,
            diagnostics=diagnostics,
        )
        
        return plan
    
    def _build_cognitive_graph(
        self,
        diagnostics: DiagnosticSnapshot,
    ) -> CognitiveGraph:
        """Build cognitive graph from diagnostics."""
        graph = CognitiveGraph()
        
        blocks = diagnostics.level1.blocks
        
        # Get L3 info if available
        l3_available = (
            diagnostics.level3.status == "available" and
            diagnostics.level3.result is not None
        )
        
        l3_result = diagnostics.level3.result if l3_available else None
        
        # Build role map for quick lookup
        role_map = {}
        if l3_result and l3_result.block_roles:
            role_map = {r.block_id: r for r in l3_result.block_roles}
        
        # 1. Add query intent as entry node
        if l3_result and l3_result.intent:
            intent = l3_result.intent
            graph.add_node(
                node_id="query_intent",
                node_type=CognitiveNodeType.REASONING_STEP,
                label=f"Intent: {intent.intent_type.value}",
                depth=0,
                is_entry=True,
            )
        else:
            # Fallback entry
            graph.add_node(
                node_id="entry",
                node_type=CognitiveNodeType.REASONING_STEP,
                label="Entry",
                depth=0,
                is_entry=True,
            )
        
        # 2. Add block nodes with appropriate types
        for i, block in enumerate(blocks):
            role = role_map.get(block.block_id)
            node_type = self._block_to_node_type(role)
            
            # Compute local complexity
            complexity = self._compute_block_complexity(block, diagnostics)
            
            graph.add_node(
                node_id=block.block_id,
                node_type=node_type,
                label=block.symbol or block.block_id,
                block_id=block.block_id,
                depth=1,
                complexity=complexity,
                metadata={
                    "tokens": block.tokens,
                    "signal_ratio": block.signal_ratio,
                },
            )
        
        # 3. Add edges based on roles and relationships
        entry_id = "query_intent" if l3_result and l3_result.intent else "entry"
        
        # Connect entry to definition blocks first
        for block in blocks:
            role = role_map.get(block.block_id)
            if role and role.primary_role.value == "DEFINE":
                graph.add_edge(
                    entry_id,
                    block.block_id,
                    CognitiveEdgeType.LEADS_TO,
                )
        
        # Connect definition blocks to implementation
        define_blocks = [b for b in blocks if role_map.get(b.block_id) and role_map[b.block_id].primary_role.value == "DEFINE"]
        impl_blocks = [b for b in blocks if role_map.get(b.block_id) and role_map[b.block_id].primary_role.value == "IMPLEMENT"]
        
        for db in define_blocks:
            for ib in impl_blocks:
                graph.add_edge(
                    db.block_id,
                    ib.block_id,
                    CognitiveEdgeType.LEADS_TO,
                )
        
        # 4. Add explanation anchors
        explain_blocks = [b for b in blocks if role_map.get(b.block_id) and role_map[b.block_id].primary_role.value == "EXPLAIN"]
        
        for eb in explain_blocks:
            # Upgrade to anchor type
            graph.add_node(
                node_id=f"anchor_{eb.block_id}",
                node_type=CognitiveNodeType.EXPLANATION_ANCHOR,
                label=f"Anchor: {eb.symbol or eb.block_id}",
                block_id=eb.block_id,
                depth=2,
            )
            
            # Connect implementations to anchors
            for ib in impl_blocks:
                graph.add_edge(
                    ib.block_id,
                    f"anchor_{eb.block_id}",
                    CognitiveEdgeType.EXPLAINS,
                )
        
        # 5. Add invariant nodes from L3 failure modes
        if l3_result:
            self._add_invariant_nodes(graph, l3_result)
        
        return graph
    
    def _block_to_node_type(self, role) -> CognitiveNodeType:
        """Map block role to cognitive node type."""
        if role is None:
            return CognitiveNodeType.REASONING_STEP
        
        role_name = role.primary_role.value
        
        mapping = {
            "DEFINE": CognitiveNodeType.REASONING_STEP,
            "IMPLEMENT": CognitiveNodeType.STATE_TRANSITION,
            "EXPLAIN": CognitiveNodeType.EXPLANATION_ANCHOR,
            "USE": CognitiveNodeType.REASONING_STEP,
            "SUPPORT": CognitiveNodeType.ASSUMPTION,
            "NOISE": CognitiveNodeType.REASONING_STEP,
        }
        
        return mapping.get(role_name, CognitiveNodeType.REASONING_STEP)
    
    def _compute_block_complexity(
        self,
        block,
        diagnostics: DiagnosticSnapshot,
    ) -> int:
        """Compute local complexity for a block."""
        complexity = 0
        
        # From structural payload
        if hasattr(block, 'structural_payload'):
            sp = block.structural_payload
            complexity += sp.nested_depth_max if hasattr(sp, 'nested_depth_max') else 0
        
        # From cognitive load if available
        if diagnostics.level3.status == "available" and diagnostics.level3.result:
            l3 = diagnostics.level3.result
            if l3.cognitive_load:
                for bl in l3.cognitive_load.block_loads:
                    if bl.block_id == block.block_id:
                        complexity += int(bl.branching_score * 3)
                        complexity += int(bl.nesting_score * 3)
                        break
        
        return complexity
    
    def _add_invariant_nodes(self, graph: CognitiveGraph, l3_result):
        """Add invariant nodes based on L3 analysis."""
        # Add invariant for role balance
        if l3_result.explanatory_balance:
            if not l3_result.explanatory_balance.is_balanced:
                graph.add_node(
                    node_id="inv_role_balance",
                    node_type=CognitiveNodeType.INVARIANT,
                    label="Maintain role balance",
                    depth=0,
                )
        
        # Add invariant for failure mode
        if l3_result.primary_failure_mode.value != "None detected":
            graph.add_node(
                node_id="inv_failure_mode",
                node_type=CognitiveNodeType.INVARIANT,
                label=f"Address: {l3_result.primary_failure_mode.value}",
                depth=0,
            )


def create_level3_engine(enabled: bool = True) -> Level3ActionEngine:
    """Factory function for dependency injection."""
    return Level3ActionEngine(enabled=enabled)


__all__ = [
    "Level3ActionEngine",
    "create_level3_engine",
]
