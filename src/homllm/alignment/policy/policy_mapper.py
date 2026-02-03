"""
Alignment Level-3 Policy Mapper

Deterministic mapping from FailureType to ResponsePolicy.

CONSTRAINTS (ABSOLUTE):
- No heuristics
- No learning
- No thresholds
- Pure mapping only
- Level-2 already decided the failure
"""

from __future__ import annotations

from ..classifier import FailureType
from .policy_types import ResponsePolicy


# =============================================================================
# Deterministic Policy Mapping (Locked)
# =============================================================================

_POLICY_MAP: dict[FailureType, ResponsePolicy] = {
    FailureType.SEMANTIC_DRIFT: ResponsePolicy(
        emphasize_runtime_behavior=True,
        require_integrated_example=True,
        suppress_structural_listing=False,
        enforce_grounded_claims=False,
        policy_confidence=0.9,
    ),
    FailureType.STRUCTURAL_GAP: ResponsePolicy(
        emphasize_runtime_behavior=False,
        require_integrated_example=False,
        suppress_structural_listing=True,
        enforce_grounded_claims=False,
        policy_confidence=0.85,
    ),
    FailureType.GROUNDING_PRESSURE: ResponsePolicy(
        emphasize_runtime_behavior=False,
        require_integrated_example=False,
        suppress_structural_listing=False,
        enforce_grounded_claims=True,
        policy_confidence=0.9,
    ),
    FailureType.OVERCONSTRAINED_CONTEXT: ResponsePolicy(
        emphasize_runtime_behavior=True,
        require_integrated_example=False,
        suppress_structural_listing=True,
        enforce_grounded_claims=False,
        policy_confidence=0.8,
    ),
    FailureType.UNDERCONSTRAINED_RESPONSE: ResponsePolicy(
        emphasize_runtime_behavior=False,
        require_integrated_example=True,
        suppress_structural_listing=False,
        enforce_grounded_claims=False,
        policy_confidence=0.75,
    ),
    FailureType.LOW_RISK: ResponsePolicy.none_policy(),
}


def map_failure_to_policy(failure: FailureType) -> ResponsePolicy:
    """
    Map a failure type to its corresponding response policy.
    
    Args:
        failure: The failure type from Level-2 classification
        
    Returns:
        ResponsePolicy for the given failure type
        
    GUARANTEES:
    - Deterministic (same input → same output)
    - No side effects
    - No computation beyond lookup
    """
    return _POLICY_MAP.get(failure, ResponsePolicy.none_policy())


__all__ = [
    "map_failure_to_policy",
]
