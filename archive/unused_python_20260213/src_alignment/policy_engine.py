"""
Alignment Level-3 Policy Engine

Converts Level-2 failure classifications into policy decisions.

CONSTRAINTS (ABSOLUTE):
- Read-only (never modifies input)
- Deterministic (same input → same output)
- No retries or regeneration
- No intelligence imports
- No prompt/context modification
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..classifier import AlignmentFailureReport

from ..classifier import FailureType
from .policy_types import ResponsePolicy, PolicyDecision
from .policy_mapper import map_failure_to_policy


class AlignmentPolicyEngine:
    """
    Level-3 policy decision engine.
    
    Consumes AlignmentFailureReport from Level-2 and produces
    PolicyDecision with machine-readable response policies.
    
    CONSTRAINTS:
    - Read-only (never modifies input)
    - Deterministic (same input → same output)
    - Stateless (no instance state affects decisions)
    - No side effects
    """
    
    def decide(self, failure_report: "AlignmentFailureReport") -> Optional[PolicyDecision]:
        """
        Decide on a response policy based on Level-2 failure report.
        
        Args:
            failure_report: Level-2 AlignmentFailureReport
            
        Returns:
            PolicyDecision if action warranted, None if LOW_RISK/no failures
            
        GUARANTEES:
        - Deterministic output
        - No side effects
        - No modification to input
        """
        # If no primary risk, no policy needed
        if failure_report.primary_risk is None:
            return None
        
        # If primary risk is LOW_RISK, no policy needed
        if failure_report.primary_risk == FailureType.LOW_RISK:
            return None
        
        # Map failure to policy
        policy = map_failure_to_policy(failure_report.primary_risk)
        
        # Attach confidence from L2
        return PolicyDecision(
            policy=policy,
            triggering_failure=failure_report.primary_risk,
            confidence=failure_report.confidence,
        )


def create_policy_engine() -> AlignmentPolicyEngine:
    """
    Factory function to create AlignmentPolicyEngine.
    
    Returns:
        Configured AlignmentPolicyEngine instance
    """
    return AlignmentPolicyEngine()


__all__ = [
    "AlignmentPolicyEngine",
    "create_policy_engine",
]
