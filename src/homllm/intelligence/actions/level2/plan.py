"""
Level-2 Semantic Action Plan Data Structures

Defines SemanticAction, SemanticObligation, SemanticGap, and SemanticActionPlan.
These are proposals for semantic completeness, NOT context mutations.

CONSTRAINTS (ABSOLUTE):
- Immutable dataclasses (frozen=True for actions)
- No mutation logic
- No LLM or ML
- No imports from generation or models
- Deterministic
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional


class SemanticActionType(IntEnum):
    """
    Semantic action types with implicit precedence.
    
    Lower value = higher precedence.
    """
    
    REQUIRE = 1       # Concept must be present; signal gap
    ENSURE = 2        # Role must be satisfied
    PROMOTE = 3       # Block should be prioritized
    COLLAPSE = 4      # Merge redundant blocks to concept
    DEPRIORITIZE = 5  # Block is semantically weaker
    REJECT = 6        # Block provides no semantic value


# Human-readable names
SEMANTIC_ACTION_NAMES: dict[SemanticActionType, str] = {
    SemanticActionType.REQUIRE: "REQUIRE",
    SemanticActionType.ENSURE: "ENSURE",
    SemanticActionType.PROMOTE: "PROMOTE",
    SemanticActionType.COLLAPSE: "COLLAPSE",
    SemanticActionType.DEPRIORITIZE: "DEPRIORITIZE",
    SemanticActionType.REJECT: "REJECT",
}


@dataclass(frozen=True)
class SemanticObligation:
    """
    A semantic requirement implied by the query.
    
    Obligations are derived from diagnostics, never invented.
    They represent what the context MUST contain to be understood.
    
    Attributes:
        name: Human-readable obligation name
        required_concepts: Concepts that must be covered
        required_roles: Explanatory roles needed (DEFINE, EXPLAIN, etc.)
        source: Which diagnostic produced this obligation
        is_satisfied: Whether obligation is currently met
    """
    
    name: str
    required_concepts: tuple[str, ...]
    required_roles: tuple[str, ...]
    source: str  # e.g., "query_intent", "concept_gaps"
    is_satisfied: bool = False


@dataclass(frozen=True)
class SemanticGap:
    """
    An unsatisfied semantic obligation.
    
    Gaps represent what is MISSING from the context.
    """
    
    obligation_name: str
    missing_concepts: tuple[str, ...]
    missing_roles: tuple[str, ...]
    severity: str  # "critical", "moderate", "minor"
    reason: str


@dataclass(frozen=True)
class SemanticAction:
    """
    A proposed semantic action.
    
    Immutable. Describes intent, not execution.
    Every action includes justification referencing diagnostics.
    
    Attributes:
        action_type: What action is proposed
        target: Target of action (concept name, block_id, or block_ids)
        justification: Why this action is proposed
        obligation_ref: Which obligation this action addresses
        diagnostic_source: Which diagnostic produced the evidence
        priority: Derived from action_type
    """
    
    action_type: SemanticActionType
    target: str  # concept name, block_id, or comma-separated block_ids
    justification: str
    obligation_ref: Optional[str] = None
    diagnostic_source: str = ""
    priority: int = field(init=False)
    
    def __post_init__(self) -> None:
        """Set priority from action_type."""
        object.__setattr__(self, "priority", int(self.action_type))
    
    @property
    def type_name(self) -> str:
        """Human-readable action type name."""
        return SEMANTIC_ACTION_NAMES.get(self.action_type, "UNKNOWN")


@dataclass
class SemanticActionPlan:
    """
    Complete semantic action plan output.
    
    Contains:
    - Ordered actions ready for consideration
    - Obligations derived from query
    - Gaps detected in context
    - Human-readable explanations
    
    This plan is IMMUTABLE after creation.
    It does NOT modify context.
    """
    
    actions: tuple[SemanticAction, ...]
    obligations: tuple[SemanticObligation, ...]
    gaps: tuple[SemanticGap, ...]
    explanations: tuple[str, ...]
    
    # Summary statistics
    total_obligations: int = 0
    satisfied_obligations: int = 0
    total_gaps: int = 0
    critical_gaps: int = 0
    
    @classmethod
    def empty(cls) -> SemanticActionPlan:
        """Create an empty plan (for disabled engine or no diagnostics)."""
        return cls(
            actions=(),
            obligations=(),
            gaps=(),
            explanations=("No semantic analysis performed",),
            total_obligations=0,
            satisfied_obligations=0,
            total_gaps=0,
            critical_gaps=0,
        )
    
    def get_actions_by_type(self, action_type: SemanticActionType) -> tuple[SemanticAction, ...]:
        """Filter actions by type."""
        return tuple(a for a in self.actions if a.action_type == action_type)
    
    @property
    def coverage_score(self) -> float:
        """Obligation satisfaction ratio."""
        if self.total_obligations == 0:
            return 1.0
        return self.satisfied_obligations / self.total_obligations


# Global action ordering for plan assembly
SEMANTIC_ACTION_ORDER: tuple[SemanticActionType, ...] = (
    SemanticActionType.REQUIRE,
    SemanticActionType.ENSURE,
    SemanticActionType.PROMOTE,
    SemanticActionType.COLLAPSE,
    SemanticActionType.DEPRIORITIZE,
    SemanticActionType.REJECT,
)


__all__ = [
    "SemanticActionType",
    "SemanticAction",
    "SemanticObligation",
    "SemanticGap",
    "SemanticActionPlan",
    "SEMANTIC_ACTION_NAMES",
    "SEMANTIC_ACTION_ORDER",
]
