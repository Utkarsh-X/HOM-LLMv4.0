"""
Alignment Level-3 Policy Types

Frozen dataclasses for response policies and policy decisions.

CONSTRAINTS (ABSOLUTE):
- All types frozen (immutable)
- JSON serializable
- No behavior logic
- No thresholds or heuristics
- Deterministic output
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..classifier import FailureType


@dataclass(frozen=True)
class ResponsePolicy:
    """
    Machine-readable response policy.
    
    Describes how an answer should ideally be framed.
    Think compiler optimization flags, not edits.
    
    Attributes:
        emphasize_runtime_behavior: Prefer runtime/dynamic explanations
        require_integrated_example: Include working code examples
        suppress_structural_listing: Avoid pure enumeration/listing
        enforce_grounded_claims: Every claim must cite context
        policy_confidence: Confidence in this policy (0-1)
    """
    
    emphasize_runtime_behavior: bool
    require_integrated_example: bool
    suppress_structural_listing: bool
    enforce_grounded_claims: bool
    policy_confidence: float
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for telemetry."""
        return {
            "emphasize_runtime_behavior": self.emphasize_runtime_behavior,
            "require_integrated_example": self.require_integrated_example,
            "suppress_structural_listing": self.suppress_structural_listing,
            "enforce_grounded_claims": self.enforce_grounded_claims,
            "policy_confidence": round(self.policy_confidence, 2),
        }
    
    def active_flags(self) -> list[str]:
        """Return list of active policy flag names."""
        flags = []
        if self.emphasize_runtime_behavior:
            flags.append("EMPHASIZE_RUNTIME")
        if self.require_integrated_example:
            flags.append("REQUIRE_EXAMPLE")
        if self.suppress_structural_listing:
            flags.append("SUPPRESS_LISTING")
        if self.enforce_grounded_claims:
            flags.append("ENFORCE_GROUNDED")
        return flags
    
    @classmethod
    def none_policy(cls) -> "ResponsePolicy":
        """Create a policy with all flags disabled."""
        return cls(
            emphasize_runtime_behavior=False,
            require_integrated_example=False,
            suppress_structural_listing=False,
            enforce_grounded_claims=False,
            policy_confidence=1.0,
        )


@dataclass(frozen=True)
class PolicyDecision:
    """
    Complete policy decision result.
    
    Produced by AlignmentPolicyEngine from Level-2 failure report.
    
    Attributes:
        policy: The response policy to apply
        triggering_failure: The failure type that triggered this policy
        confidence: Confidence in this decision (from L2)
    """
    
    policy: ResponsePolicy
    triggering_failure: "FailureType"
    confidence: float
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for telemetry."""
        return {
            "policy": self.policy.to_dict(),
            "triggering_failure": self.triggering_failure.value,
            "confidence": round(self.confidence, 2),
            "active_flags": self.policy.active_flags(),
        }


__all__ = [
    "ResponsePolicy",
    "PolicyDecision",
]
