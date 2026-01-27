"""
Reasoning Contract Layer - Data Structures

Read-only data structures for reasoning contracts.
Contracts define explicit reasoning obligations that MUST be
satisfied, without altering generation behavior.

CONSTRAINTS (ABSOLUTE):
- All types are frozen (immutable)
- No behavior logic
- No thresholds or probabilities
- Purely declarative
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ReasoningStep(Enum):
    """
    Types of reasoning steps that may be required.
    
    These are declarative obligations, not execution steps.
    """
    
    ENUMERATION_REQUIRED = "enumeration_required"     # Must enumerate items
    INTERACTION_REQUIRED = "interaction_required"     # Must explain interactions
    TRACE_REQUIRED = "trace_required"                 # Must trace execution flow
    COMPLETENESS_REQUIRED = "completeness_required"   # Must cover available context


class ContractSeverity(Enum):
    """
    Severity level for reasoning contracts.
    """
    
    REQUIRED = "required"    # Must be satisfied
    ADVISORY = "advisory"    # Recommended, non-blocking


@dataclass(frozen=True)
class Constraint:
    """
    A single reasoning constraint within a contract.
    
    Attributes:
        step: The required reasoning step
        reason: Human-readable explanation of why this is required
        evidence_count: Number of blocks/components supporting this
    """
    
    step: ReasoningStep
    reason: str
    evidence_count: int = 0


@dataclass(frozen=True)
class ReasoningContract:
    """
    Complete reasoning contract for a query.
    
    Declares what reasoning MUST occur before the answer
    can be considered complete.
    
    Attributes:
        required_steps: Tuple of required reasoning steps
        constraints: Detailed constraints with reasons
        severity: Whether contract is required or advisory
    """
    
    required_steps: tuple[ReasoningStep, ...]
    constraints: tuple[Constraint, ...]
    severity: ContractSeverity
    
    @classmethod
    def empty(cls) -> "ReasoningContract":
        """Create an empty contract with no requirements."""
        return cls(
            required_steps=(),
            constraints=(),
            severity=ContractSeverity.ADVISORY,
        )
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for telemetry output."""
        return {
            "required_steps": [s.value for s in self.required_steps],
            "constraints": [
                {
                    "step": c.step.value,
                    "reason": c.reason,
                    "evidence_count": c.evidence_count,
                }
                for c in self.constraints
            ],
            "severity": self.severity.value,
        }
    
    @property
    def has_requirements(self) -> bool:
        """Check if contract has any requirements."""
        return len(self.required_steps) > 0
    
    @property
    def step_names(self) -> list[str]:
        """Get list of step names for telemetry."""
        return [s.value.upper() for s in self.required_steps]


__all__ = [
    "ReasoningStep",
    "ContractSeverity",
    "Constraint",
    "ReasoningContract",
]
