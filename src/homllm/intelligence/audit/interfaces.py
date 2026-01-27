"""
Assertion Suppression Audit - Data Structures

Read-only data structures for assertion suppression analysis.
This module defines the output types for the audit layer.

CONSTRAINTS (ABSOLUTE):
- All types are frozen (immutable)
- No behavior logic
- No dependencies on action engines
- Purely descriptive
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AssertionCandidate:
    """
    A potential assertion that could be made about a block.
    
    Assertions are derived from block diagnostics and represent
    claims the LLM could state about the code.
    
    Attributes:
        assertion_id: Unique identifier (derived from block_id + claim type)
        textual_form: Human-readable claim description
        supporting_blocks: Block IDs that support this assertion
        confidence_signal: Derived confidence (0.0-1.0), not used for logic
    """
    
    assertion_id: str
    textual_form: str
    supporting_blocks: tuple[str, ...]
    confidence_signal: float = 0.0


@dataclass(frozen=True)
class SuppressionReason:
    """
    Explains why an assertion was suppressed.
    
    Attributes:
        level: Intelligence level (1, 2, or 3)
        rule_name: Name of the rule that caused suppression
        action_type: Action type (PROTECT, PRESERVE, ANCHOR, KEEP, DROP, etc.)
        blocking_block_id: Block ID that triggered the suppression
        explanation: Human-readable explanation
    """
    
    level: int
    rule_name: str
    action_type: str
    blocking_block_id: str
    explanation: str


@dataclass(frozen=True)
class AssertionAuditEntry:
    """
    Audit entry for a single assertion.
    
    Combines the assertion candidate with its suppression status.
    """
    
    assertion: AssertionCandidate
    is_suppressed: bool
    suppression_reasons: tuple[SuppressionReason, ...] = ()


@dataclass(frozen=True)
class AuditResult:
    """
    Complete audit result for assertion suppression analysis.
    
    This is the primary output of the AuditCollector.
    Contains aggregate statistics and per-assertion details.
    
    Attributes:
        total_assertions_considered: Number of potential assertions analyzed
        assertions_suppressed: Number of assertions blocked by actions
        assertions_unblocked: Number of assertions that can be made
        suppression_breakdown_by_level: Count of suppressions per level
        entries: Detailed per-assertion audit entries
    """
    
    total_assertions_considered: int
    assertions_suppressed: int
    assertions_unblocked: int
    suppression_breakdown_by_level: tuple[tuple[int, int], ...]  # ((level, count), ...)
    entries: tuple[AssertionAuditEntry, ...] = ()
    
    @classmethod
    def empty(cls) -> "AuditResult":
        """Create an empty audit result."""
        return cls(
            total_assertions_considered=0,
            assertions_suppressed=0,
            assertions_unblocked=0,
            suppression_breakdown_by_level=(),
            entries=(),
        )
    
    def to_dict(self) -> dict:
        """
        Serialize to dictionary for telemetry output.
        
        Returns JSON-serializable representation.
        """
        return {
            "total_assertions_considered": self.total_assertions_considered,
            "assertions_suppressed": self.assertions_suppressed,
            "assertions_unblocked": self.assertions_unblocked,
            "suppression_breakdown_by_level": {
                level: count for level, count in self.suppression_breakdown_by_level
            },
            "entries": [
                {
                    "assertion_id": entry.assertion.assertion_id,
                    "textual_form": entry.assertion.textual_form,
                    "is_suppressed": entry.is_suppressed,
                    "suppression_reasons": [
                        {
                            "level": r.level,
                            "rule_name": r.rule_name,
                            "action_type": r.action_type,
                            "blocking_block_id": r.blocking_block_id,
                            "explanation": r.explanation,
                        }
                        for r in entry.suppression_reasons
                    ],
                }
                for entry in self.entries
            ],
        }


__all__ = [
    "AssertionCandidate",
    "SuppressionReason",
    "AssertionAuditEntry",
    "AuditResult",
]
