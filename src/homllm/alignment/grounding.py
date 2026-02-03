"""
Grounding Alignment Computation - GCS

Grounding Coverage Signal computation.
Estimates whether context can support expected claim count.

CONSTRAINTS:
- Read-only, deterministic
- No hallucination detection
- No blocking behavior
- Just ratios and counts
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact
    from homllm.intelligence.reasoning_contracts.interfaces import ReasoningContract
    from homllm.intelligence.assertion_readability.interfaces import ReadabilityResult

from .interfaces import GroundingAlignment


# Claim estimation multipliers (deterministic, not tuneable)
_CLAIMS_PER_ENUMERATION_STEP = 3
_CLAIMS_PER_INTERACTION_STEP = 4
_CLAIMS_PER_TRACE_STEP = 5
_CLAIMS_PER_COMPLETENESS_STEP = 2
_CLAIMS_BASE = 2  # Base claims for any answer

# Capacity estimation (deterministic, not tuneable)
_REFS_PER_READABLE_BLOCK = 2
_REFS_PER_DISTINCT_COMPONENT = 1


def compute_grounding_alignment(
    context_artifact: "ContextArtifact",
    reasoning_contract: Optional["ReasoningContract"],
    readability_result: Optional["ReadabilityResult"],
) -> GroundingAlignment:
    """
    Compute Grounding Coverage Signal.
    
    Args:
        context_artifact: Assembled context with blocks
        reasoning_contract: Contract defining required reasoning steps
        readability_result: Assertion readability evaluation
        
    Returns:
        GroundingAlignment with claim count, capacity, and ratio
        
    GUARANTEES:
    - Deterministic (same input → same output)
    - No side effects
    - No hallucination detection
    """
    # Estimate expected claim count from reasoning contract
    estimated_claims = _CLAIMS_BASE
    
    if reasoning_contract and reasoning_contract.has_requirements:
        for step in reasoning_contract.required_steps:
            step_value = step.value.lower()
            if "enumeration" in step_value:
                estimated_claims += _CLAIMS_PER_ENUMERATION_STEP
            elif "interaction" in step_value:
                estimated_claims += _CLAIMS_PER_INTERACTION_STEP
            elif "trace" in step_value:
                estimated_claims += _CLAIMS_PER_TRACE_STEP
            elif "completeness" in step_value:
                estimated_claims += _CLAIMS_PER_COMPLETENESS_STEP
    
    # Measure grounding capacity from readable blocks and components
    readable_count = 0
    if readability_result:
        readable_count = readability_result.readable_count
    
    distinct_components = len(set(
        block.file for block in context_artifact.blocks
    )) if context_artifact.blocks else 0
    
    grounding_capacity = (
        readable_count * _REFS_PER_READABLE_BLOCK +
        distinct_components * _REFS_PER_DISTINCT_COMPONENT
    )
    
    # Compute pressure ratio (higher = more pressure, potential grounding issues)
    if grounding_capacity > 0:
        pressure_ratio = estimated_claims / grounding_capacity
    else:
        # No grounding capacity means infinite pressure (represented as high value)
        pressure_ratio = float(estimated_claims) if estimated_claims > 0 else 0.0
    
    return GroundingAlignment(
        estimated_claim_count=estimated_claims,
        grounding_reference_capacity=grounding_capacity,
        grounding_pressure_ratio=pressure_ratio,
    )


__all__ = ["compute_grounding_alignment"]
