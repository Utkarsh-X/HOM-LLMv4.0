"""
Structural Alignment Computation - SEG

Structural Expectation Gap signal computation.
Exposes whether expected answer structure is supported
by available context.

CONSTRAINTS:
- Read-only, deterministic
- No interpretation logic
- No scoring, just counts and flags
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact
    from homllm.intelligence.reasoning_contracts.interfaces import ReasoningContract
    from homllm.intelligence.assertion_readability.interfaces import ReadabilityResult

from .interfaces import StructuralAlignment


def compute_structural_alignment(
    context_artifact: "ContextArtifact",
    reasoning_contract: Optional["ReasoningContract"],
    readability_result: Optional["ReadabilityResult"],
) -> StructuralAlignment:
    """
    Compute Structural Expectation Gap signals.
    
    Args:
        context_artifact: Assembled context with blocks
        reasoning_contract: Contract defining required reasoning steps
        readability_result: Assertion readability evaluation
        
    Returns:
        StructuralAlignment with counts and support matrix
        
    GUARANTEES:
    - Deterministic (same input → same output)
    - No side effects
    - No interpretation logic
    """
    # Count expected reasoning steps
    expected_steps = 0
    step_names: list[str] = []
    
    if reasoning_contract and reasoning_contract.has_requirements:
        expected_steps = len(reasoning_contract.required_steps)
        step_names = [s.value for s in reasoning_contract.required_steps]
    
    # Count readable blocks
    readable_count = 0
    if readability_result:
        readable_count = readability_result.readable_count
    
    # Count distinct components (unique files)
    distinct_components = len(set(
        block.file for block in context_artifact.blocks
    )) if context_artifact.blocks else 0
    
    # Build structural support matrix
    # For each required step, determine if context can support it
    support_matrix: dict[str, bool] = {}
    
    for step_name in step_names:
        # Simple heuristic: step is supported if we have readable blocks
        # and distinct components relevant to step type
        if "enumeration" in step_name:
            # Enumeration requires multiple distinct components
            support_matrix[step_name] = distinct_components >= 2 and readable_count > 0
        elif "interaction" in step_name:
            # Interaction requires at least 2 components
            support_matrix[step_name] = distinct_components >= 2 and readable_count >= 2
        elif "trace" in step_name:
            # Trace requires readable code blocks
            support_matrix[step_name] = readable_count >= 1
        elif "completeness" in step_name:
            # Completeness requires sufficient coverage
            support_matrix[step_name] = readable_count >= 3
        else:
            # Unknown step type: conservatively mark as supported if we have context
            support_matrix[step_name] = readable_count > 0
    
    return StructuralAlignment(
        expected_reasoning_steps=expected_steps,
        readable_block_count=readable_count,
        distinct_component_count=distinct_components,
        structural_support_matrix=support_matrix,
    )


__all__ = ["compute_structural_alignment"]
