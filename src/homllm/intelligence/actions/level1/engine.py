"""
Level-1 Action Intelligence Engine

Main orchestrator that:
1. Reads Level-1 structural diagnostics
2. Evaluates all rules on each block
3. Resolves conflicts deterministically
4. Produces an ordered, auditable ContextModificationPlan

CONSTRAINTS (ABSOLUTE):
- NEVER interpret meaning
- NEVER call LLMs
- NEVER mutate context directly
- ONLY propose structural actions based on diagnostics
- Deterministic: same input → same output
- Can be safely disabled or replayed
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homllm.intelligence.actions.level1.plan import (
    Action,
    ActionType,
    ContextModificationPlan,
    ProposedAction,
    ACTION_TYPE_NAMES,
)
from homllm.intelligence.actions.level1.rules import get_all_rules
from homllm.intelligence.actions.level1.resolver import (
    ConflictResolver,
    order_actions,
)

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact
    from homllm.intelligence.interfaces import DiagnosticSnapshot
    from homllm.intelligence.diagnostics.inspect_context import IntraBlockDiagnostic


class Level1ActionEngine:
    """
    Level-1 Action Intelligence Engine.
    
    This engine is LLVM-O1, not GPT-4.
    It performs structural optimization, not reasoning.
    
    Usage:
        engine = Level1ActionEngine(enabled=True)
        plan = engine.propose(diagnostics, context)
        
        # Plan contains ordered actions, not mutations
        for action in plan.actions:
            print(f"{action.block_id}: {action.type_name} - {action.reason}")
    
    Attributes:
        enabled: If False, propose() returns empty plan immediately
    """
    
    def __init__(self, enabled: bool = True):
        """
        Initialize the engine.
        
        Args:
            enabled: If False, engine is disabled and returns empty plans.
                     Useful for A/B testing or gradual rollout.
        """
        self.enabled = enabled
        self._resolver = ConflictResolver()
        self._rules = get_all_rules()
    
    def propose(
        self,
        diagnostics: DiagnosticSnapshot,
        context: ContextArtifact,
    ) -> ContextModificationPlan:
        """
        Propose structural actions based on diagnostics.
        
        This method is the ONLY entry point for the engine.
        It does NOT execute actions, only proposes them.
        
        Args:
            diagnostics: DiagnosticSnapshot with level1 available
            context: ContextArtifact being analyzed (read-only)
            
        Returns:
            ContextModificationPlan with ordered actions
            
        Note:
            - If engine is disabled, returns empty plan
            - If L1 diagnostics unavailable, returns empty plan
            - Plan is deterministic: same input → same output
        """
        # Check if engine is enabled
        if not self.enabled:
            return ContextModificationPlan.empty()
        
        # Check if L1 diagnostics are available
        if diagnostics.level1.status != "available":
            return ContextModificationPlan.empty()
        
        # Get blocks from L1 diagnostics
        blocks = diagnostics.level1.blocks
        if not blocks:
            return ContextModificationPlan.empty()
        
        # Phase 1: Rule Evaluation
        proposals_by_block = self._evaluate_rules(blocks)
        
        # Phase 2: Conflict Resolution
        final_actions, conflicts_count = self._resolver.resolve(proposals_by_block)
        
        # Phase 3: Global Ordering
        ordered_actions = order_actions(final_actions)
        
        # Build summary
        summary = self._build_summary(ordered_actions)
        
        return ContextModificationPlan(
            actions=ordered_actions,
            summary=summary,
            total_blocks_analyzed=len(blocks),
            conflicts_resolved=conflicts_count,
        )
    
    def _evaluate_rules(
        self,
        blocks: tuple[IntraBlockDiagnostic, ...]
    ) -> dict[str, list[ProposedAction]]:
        """
        Evaluate all rules on all blocks.
        
        Returns:
            Map of block_id → list of proposed actions
        """
        proposals_by_block: dict[str, list[ProposedAction]] = {}
        
        for block in blocks:
            block_proposals: list[ProposedAction] = []
            
            for rule_name, rule_fn in self._rules:
                try:
                    rule_proposals = rule_fn(block)
                    block_proposals.extend(rule_proposals)
                except Exception:
                    # Rules must never crash the engine
                    # Skip failed rules silently (could log in future)
                    pass
            
            if block_proposals:
                proposals_by_block[block.block_id] = block_proposals
        
        return proposals_by_block
    
    def _build_summary(self, actions: tuple[Action, ...]) -> dict[str, int]:
        """Build summary counts per action type."""
        summary = {name: 0 for name in ACTION_TYPE_NAMES.values()}
        
        for action in actions:
            type_name = ACTION_TYPE_NAMES.get(action.action_type, "UNKNOWN")
            summary[type_name] = summary.get(type_name, 0) + 1
        
        return summary


# Factory function for dependency injection
def create_level1_engine(enabled: bool = True) -> Level1ActionEngine:
    """
    Create a Level1ActionEngine instance.
    
    Args:
        enabled: Whether the engine is active
        
    Returns:
        Configured Level1ActionEngine
    """
    return Level1ActionEngine(enabled=enabled)


__all__ = [
    "Level1ActionEngine",
    "create_level1_engine",
]
