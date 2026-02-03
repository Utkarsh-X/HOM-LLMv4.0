"""
Alignment Level-3 Policy Decision Layer

Deterministic, read-only policy decision layer that converts
Level-2 failure classifications into machine-readable response policies.

CONSTRAINTS (ABSOLUTE):
- Read-only (no context/prompt/generation modification)
- Deterministic (same input → same policy)
- No retries or regeneration
- No intelligence imports
- Fully removable with zero side effects

USAGE:
    from homllm.alignment.policy import create_policy_engine
    
    engine = create_policy_engine()
    decision = engine.decide(failure_report)
    if decision:
        flags = decision.policy.active_flags()
"""

from .policy_types import ResponsePolicy, PolicyDecision
from .policy_engine import AlignmentPolicyEngine, create_policy_engine


__all__ = [
    # Types
    "ResponsePolicy",
    "PolicyDecision",
    # Engine
    "AlignmentPolicyEngine",
    # Factory
    "create_policy_engine",
]
