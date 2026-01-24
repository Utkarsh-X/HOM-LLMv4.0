"""
Level-3 Cognitive Action Plan Data Structures

Defines CognitiveAction, ReasoningPath, and CognitiveActionPlan.
These are shaping actions that control reasoning topology, NOT content mutations.

The goal: Make correct reasoning structurally unavoidable for the LLM.

CONSTRAINTS (ABSOLUTE):
- Immutable dataclasses (frozen=True)
- No mutation logic
- No LLM or ML
- No agent loops or recursion
- No learning or memory
- Deterministic
- Auditable (every action has justification)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional


class CognitiveActionType(IntEnum):
    """
    Cognitive shaping action types with implicit precedence.
    
    Lower value = higher precedence.
    These actions shape reasoning topology, not content.
    """
    
    ORDER = 1       # Control reasoning sequence
    PRESERVE = 2    # Protect invariant blocks
    ANCHOR = 3      # Establish explanation anchors
    LIMIT = 4       # Reduce branching complexity
    ISOLATE = 5     # Separate deep/complex logic
    SEPARATE = 6    # Separate mixed concerns


# Human-readable names
COGNITIVE_ACTION_NAMES: dict[CognitiveActionType, str] = {
    CognitiveActionType.ORDER: "ORDER",
    CognitiveActionType.PRESERVE: "PRESERVE",
    CognitiveActionType.ANCHOR: "ANCHOR",
    CognitiveActionType.LIMIT: "LIMIT",
    CognitiveActionType.ISOLATE: "ISOLATE",
    CognitiveActionType.SEPARATE: "SEPARATE",
}


@dataclass(frozen=True)
class ReasoningStep:
    """
    A single step in a reasoning path.
    
    Represents a logical unit in the reasoning chain.
    """
    
    step_id: str
    step_type: str  # "entry", "decision", "implementation", "anchor"
    block_id: Optional[str] = None
    description: str = ""


@dataclass(frozen=True)
class ReasoningPath:
    """
    A sequence of reasoning steps with associated invariants.
    
    Extracted from query intent through semantic obligations.
    """
    
    path_id: str
    steps: tuple[ReasoningStep, ...]
    invariants: tuple[str, ...]  # Invariant identifiers
    entry_point: str
    exit_point: str
    complexity: int = 0  # Number of decision points


@dataclass(frozen=True)
class CognitiveAction:
    """
    A proposed cognitive shaping action.
    
    Immutable. Shapes reasoning topology, not content.
    Every action includes justification referencing diagnostics.
    
    Attributes:
        action_type: What shaping to apply
        target: Target (block_id, path_id, or relation)
        parameters: Action-specific parameters
        justification: Why this shaping is needed
        diagnostic_source: Which diagnostic produced the evidence
        priority: Derived from action_type
    """
    
    action_type: CognitiveActionType
    target: str
    parameters: tuple[tuple[str, Any], ...] = ()  # Frozen dict
    justification: str = ""
    diagnostic_source: str = ""
    priority: int = field(init=False)
    
    def __post_init__(self) -> None:
        """Set priority from action_type."""
        object.__setattr__(self, "priority", int(self.action_type))
    
    @property
    def type_name(self) -> str:
        """Human-readable action type name."""
        return COGNITIVE_ACTION_NAMES.get(self.action_type, "UNKNOWN")
    
    @property
    def params_dict(self) -> dict[str, Any]:
        """Convert parameters to dict."""
        return dict(self.parameters)


@dataclass(frozen=True)
class InvariantProtection:
    """
    An invariant to be protected during reasoning.
    
    Invariants are constraints that must hold throughout reasoning.
    """
    
    invariant_id: str
    invariant_type: str  # "precedence", "ordering", "safety", "constraint"
    description: str
    protected_blocks: tuple[str, ...]
    source: str  # Which diagnostic identified this


@dataclass(frozen=True)
class AmbiguityIsolation:
    """
    An ambiguous region to be isolated.
    
    Ambiguity sources: mixed responsibilities, conflicting abstractions,
    similar identifiers, overlapping explanations.
    """
    
    isolation_id: str
    ambiguity_type: str  # "mixed_responsibility", "conflicting", "similar_names", "overlap"
    affected_blocks: tuple[str, ...]
    reason: str


@dataclass
class CognitiveActionPlan:
    """
    Complete cognitive shaping plan output.
    
    Contains:
    - Ordered shaping actions
    - Extracted reasoning paths
    - Protected invariants
    - Isolated ambiguities
    - Human-readable explanations
    
    This plan shapes reasoning topology, it does NOT modify code.
    """
    
    actions: tuple[CognitiveAction, ...]
    reasoning_paths: tuple[ReasoningPath, ...]
    invariants: tuple[InvariantProtection, ...]
    ambiguities: tuple[AmbiguityIsolation, ...]
    explanations: tuple[str, ...]
    
    # Summary statistics
    total_paths: int = 0
    max_path_complexity: int = 0
    invariant_count: int = 0
    ambiguity_count: int = 0
    
    @classmethod
    def empty(cls) -> CognitiveActionPlan:
        """Create an empty plan (for disabled engine or no diagnostics)."""
        return cls(
            actions=(),
            reasoning_paths=(),
            invariants=(),
            ambiguities=(),
            explanations=("No cognitive shaping performed",),
            total_paths=0,
            max_path_complexity=0,
            invariant_count=0,
            ambiguity_count=0,
        )
    
    def get_actions_by_type(self, action_type: CognitiveActionType) -> tuple[CognitiveAction, ...]:
        """Filter actions by type."""
        return tuple(a for a in self.actions if a.action_type == action_type)
    
    @property
    def has_high_complexity(self) -> bool:
        """Check if any path has high complexity."""
        return self.max_path_complexity > 3
    
    @property
    def needs_linearization(self) -> bool:
        """Check if reasoning needs linearization."""
        return (
            self.max_path_complexity > 2 or
            self.ambiguity_count > 0
        )


# Global action ordering for plan assembly
COGNITIVE_ACTION_ORDER: tuple[CognitiveActionType, ...] = (
    CognitiveActionType.ORDER,
    CognitiveActionType.PRESERVE,
    CognitiveActionType.ANCHOR,
    CognitiveActionType.LIMIT,
    CognitiveActionType.ISOLATE,
    CognitiveActionType.SEPARATE,
)


__all__ = [
    "CognitiveActionType",
    "CognitiveAction",
    "ReasoningStep",
    "ReasoningPath",
    "InvariantProtection",
    "AmbiguityIsolation",
    "CognitiveActionPlan",
    "COGNITIVE_ACTION_NAMES",
    "COGNITIVE_ACTION_ORDER",
]
