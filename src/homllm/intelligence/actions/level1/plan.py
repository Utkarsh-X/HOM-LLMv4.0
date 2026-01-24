"""
Level-1 Action Plan Data Structures

Defines Action and ContextModificationPlan - the output of the Level-1 engine.
Actions are proposals, NOT mutations. They describe what COULD be done, not what WAS done.

CONSTRAINTS (ABSOLUTE):
- Immutable dataclasses (frozen=True for Action)
- No mutation logic
- No imports from generation or models
- No semantic inference
- Deterministic
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class ActionType(IntEnum):
    """
    Action types with implicit precedence.
    
    Lower value = higher precedence.
    Used for conflict resolution: PROTECT always wins over DROP.
    """
    
    PROTECT = 1      # Never modify this block
    KEEP = 2         # Retain as-is in context
    COMPACT = 3      # Reduce verbosity (remove comments/logging)
    DEDUPE = 4       # Merge with similar blocks
    DOWNWEIGHT = 5   # Reduce priority in ranking
    DROP = 6         # Remove from context


# Mapping for human-readable names
ACTION_TYPE_NAMES: dict[ActionType, str] = {
    ActionType.PROTECT: "PROTECT",
    ActionType.KEEP: "KEEP",
    ActionType.COMPACT: "COMPACT",
    ActionType.DEDUPE: "DEDUPE",
    ActionType.DOWNWEIGHT: "DOWNWEIGHT",
    ActionType.DROP: "DROP",
}


@dataclass(frozen=True)
class Action:
    """
    A proposed action on a context block.
    
    Immutable. Describes intent, not execution.
    Every action includes full auditability: reason, confidence, 
    originating rule, and diagnostic evidence.
    
    Attributes:
        block_id: Target block identifier
        action_type: What action is proposed
        reason: Human-readable explanation
        confidence: 0.0-1.0, higher = more certain
        originating_rule: Name of rule that produced this action
        diagnostic_evidence: Structured reference to diagnostic values
        priority: Derived from action_type for ordering (lower = first)
    """
    
    block_id: str
    action_type: ActionType
    reason: str
    confidence: float
    originating_rule: str
    diagnostic_evidence: tuple[tuple[str, Any], ...]  # Frozen dict alternative
    priority: int = field(init=False)
    
    def __post_init__(self) -> None:
        """Set priority from action_type."""
        # Use object.__setattr__ because dataclass is frozen
        object.__setattr__(self, "priority", int(self.action_type))
    
    @property
    def evidence_dict(self) -> dict[str, Any]:
        """Convert frozen evidence to dict for display."""
        return dict(self.diagnostic_evidence)
    
    @property
    def type_name(self) -> str:
        """Human-readable action type name."""
        return ACTION_TYPE_NAMES.get(self.action_type, "UNKNOWN")


@dataclass(frozen=True)
class ProposedAction:
    """
    Intermediate action from a single rule.
    
    Used internally during rule evaluation before conflict resolution.
    Converted to Action after resolver selects the winning proposal.
    """
    
    block_id: str
    action_type: ActionType
    confidence: float
    reason: str
    originating_rule: str
    evidence: tuple[tuple[str, Any], ...]


@dataclass
class ContextModificationPlan:
    """
    The complete action plan for a context.
    
    Contains ordered actions ready for execution (by a separate executor).
    This plan is the ONLY output of the Level-1 engine.
    
    Ordering guarantees:
    1. PROTECT actions first (preserve critical blocks)
    2. DEDUPE actions second (remove duplicates before compacting)
    3. COMPACT actions third (reduce verbosity)
    4. DOWNWEIGHT actions fourth (adjust priorities)
    5. DROP actions last (remove after all other operations)
    
    Attributes:
        actions: Ordered tuple of finalized actions
        summary: Counts per action type for quick inspection
        total_blocks_analyzed: Number of blocks the engine processed
        conflicts_resolved: Number of blocks with multiple proposals
    """
    
    actions: tuple[Action, ...]
    summary: dict[str, int]
    total_blocks_analyzed: int = 0
    conflicts_resolved: int = 0
    
    @classmethod
    def empty(cls) -> ContextModificationPlan:
        """Create an empty plan (for disabled engine or no blocks)."""
        return cls(
            actions=(),
            summary={name: 0 for name in ACTION_TYPE_NAMES.values()},
            total_blocks_analyzed=0,
            conflicts_resolved=0,
        )
    
    def get_actions_by_type(self, action_type: ActionType) -> tuple[Action, ...]:
        """Filter actions by type."""
        return tuple(a for a in self.actions if a.action_type == action_type)
    
    def get_action_for_block(self, block_id: str) -> Action | None:
        """Get the final action for a specific block."""
        for action in self.actions:
            if action.block_id == block_id:
                return action
        return None


# Global action ordering for plan assembly
# Actions are sorted by this order within the final plan
ACTION_GLOBAL_ORDER: tuple[ActionType, ...] = (
    ActionType.PROTECT,
    ActionType.DEDUPE,
    ActionType.COMPACT,
    ActionType.DOWNWEIGHT,
    ActionType.DROP,
)


__all__ = [
    "ActionType",
    "Action",
    "ProposedAction",
    "ContextModificationPlan",
    "ACTION_TYPE_NAMES",
    "ACTION_GLOBAL_ORDER",
]
