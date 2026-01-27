"""
Assertion Readability Model - Data Structures

Read-only data structures for assertion readability evaluation.
This module defines types that determine whether a context block
may be asserted by the LLM, separating mutability safety from
epistemic usability.

CONSTRAINTS (ABSOLUTE):
- All types are frozen (immutable)
- No behavior logic
- No thresholds or probabilities
- Purely descriptive
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ReadabilityReason(Enum):
    """
    Reasons why a block is or is not readable.
    
    These are binary deterministic categories, not scores.
    """
    
    # Readable reasons
    EXPLICIT_DEFINITION = "explicit_definition"       # Contains function/class definition
    ORDERED_LOGIC = "ordered_logic"                   # Has explicit ordering/priority/enums
    CONTROL_FLOW = "control_flow"                     # Contains conditionals/loops
    SIMPLE_STATE_TRANSITION = "state_transition"      # Clear state changes
    PROTECTED_BUT_READABLE = "protected_but_readable" # Has protection but still readable
    
    # Not readable reasons
    TOO_FRAGMENTED = "too_fragmented"                 # Block is fragmented utility code
    IMPLICIT_ONLY = "implicit_only"                   # No visible effect, implicit behavior


@dataclass(frozen=True)
class AssertionReadability:
    """
    Readability assessment for a single block.
    
    Determines whether the block's content can be asserted by the LLM,
    regardless of whether it is protected by intelligence actions.
    
    Attributes:
        block_id: Unique identifier for the block
        readable: Whether the block content can be asserted
        reasons: Tuple of reasons explaining the readability decision
        protecting_actions: Actions that protect but don't silence this block
    """
    
    block_id: str
    readable: bool
    reasons: tuple[ReadabilityReason, ...]
    protecting_actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReadabilityResult:
    """
    Complete readability evaluation result.
    
    Aggregates readability assessments for all blocks in context.
    
    Attributes:
        total_blocks: Number of blocks evaluated
        readable_count: Blocks that can be asserted
        suppressed_count: Blocks that cannot be asserted
        protected_but_readable_count: Protected blocks that are still readable
        entries: Per-block readability assessments
    """
    
    total_blocks: int
    readable_count: int
    suppressed_count: int
    protected_but_readable_count: int
    entries: tuple[AssertionReadability, ...]
    
    @classmethod
    def empty(cls) -> "ReadabilityResult":
        """Create an empty readability result."""
        return cls(
            total_blocks=0,
            readable_count=0,
            suppressed_count=0,
            protected_but_readable_count=0,
            entries=(),
        )
    
    def to_dict(self) -> dict:
        """
        Serialize to dictionary for telemetry output.
        
        Returns JSON-serializable representation.
        """
        return {
            "total_blocks": self.total_blocks,
            "readable_count": self.readable_count,
            "suppressed_count": self.suppressed_count,
            "protected_but_readable_count": self.protected_but_readable_count,
            "entries": [
                {
                    "block_id": entry.block_id,
                    "readable": entry.readable,
                    "reasons": [r.value for r in entry.reasons],
                    "protecting_actions": list(entry.protecting_actions),
                }
                for entry in self.entries
            ],
        }


__all__ = [
    "ReadabilityReason",
    "AssertionReadability",
    "ReadabilityResult",
]
