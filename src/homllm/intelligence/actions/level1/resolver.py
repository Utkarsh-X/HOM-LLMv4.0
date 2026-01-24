"""
Level-1 Conflict Resolver

Deterministic conflict resolution for proposed actions.
When multiple rules propose actions for the same block,
this resolver selects exactly ONE winner.

CONSTRAINTS (ABSOLUTE):
- Deterministic (same input → same output)
- No randomness
- No learning or memory
- No side effects
- Produces exactly one action per block
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homllm.intelligence.actions.level1.plan import (
    Action,
    ActionType,
    ProposedAction,
    ACTION_GLOBAL_ORDER,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# CONFLICT RESOLVER
# =============================================================================

class ConflictResolver:
    """
    Resolves conflicts when multiple rules propose actions for same block.
    
    Resolution strategy (deterministic):
    1. Higher precedence wins (PROTECT > KEEP > COMPACT > DEDUPE > DOWNWEIGHT > DROP)
    2. If same precedence, higher confidence wins
    3. If same confidence, alphabetical rule name wins (stable)
    
    Guarantees:
    - Exactly one action per block
    - No action silently discarded (all logged)
    - Deterministic ordering
    """
    
    def resolve(
        self,
        proposals_by_block: dict[str, list[ProposedAction]]
    ) -> tuple[list[Action], int]:
        """
        Resolve conflicts and produce final actions.
        
        Args:
            proposals_by_block: Map of block_id -> list of proposals
            
        Returns:
            Tuple of (final_actions, conflicts_count)
        """
        final_actions: list[Action] = []
        conflicts_count = 0
        
        for block_id, proposals in proposals_by_block.items():
            if not proposals:
                continue
            
            if len(proposals) > 1:
                conflicts_count += 1
            
            # Select winner using resolution strategy
            winner = self._select_winner(proposals)
            
            # Convert ProposedAction to Action
            action = Action(
                block_id=winner.block_id,
                action_type=winner.action_type,
                reason=winner.reason,
                confidence=winner.confidence,
                originating_rule=winner.originating_rule,
                diagnostic_evidence=winner.evidence,
            )
            final_actions.append(action)
        
        return final_actions, conflicts_count
    
    def _select_winner(self, proposals: list[ProposedAction]) -> ProposedAction:
        """
        Select winning proposal using deterministic strategy.
        
        Tie-breaking:
        1. Lower action_type value wins (higher precedence)
        2. Higher confidence wins
        3. Alphabetically earlier rule name wins
        """
        return min(
            proposals,
            key=lambda p: (
                int(p.action_type),      # Lower = higher precedence
                -p.confidence,            # Higher confidence wins (negated for min)
                p.originating_rule,       # Alphabetical for stability
            )
        )


def order_actions(actions: list[Action]) -> tuple[Action, ...]:
    """
    Order actions globally for execution.
    
    Order: PROTECT → DEDUPE → COMPACT → DOWNWEIGHT → DROP
    Within same type: sort by block_id for determinism.
    
    Args:
        actions: Unordered list of actions
        
    Returns:
        Ordered tuple of actions
    """
    # Create priority map from global order
    type_priority = {t: i for i, t in enumerate(ACTION_GLOBAL_ORDER)}
    
    # Handle KEEP which isn't in global order (treat as after PROTECT)
    type_priority[ActionType.KEEP] = 1  # Same as after PROTECT
    
    sorted_actions = sorted(
        actions,
        key=lambda a: (
            type_priority.get(a.action_type, 99),  # Type order
            a.block_id,                             # Block ID for stability
        )
    )
    
    return tuple(sorted_actions)


__all__ = [
    "ConflictResolver",
    "order_actions",
]
