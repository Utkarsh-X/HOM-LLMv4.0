"""
Reasoning Contract Builder

Builds reasoning contracts from diagnostic results.
Converts detected expectations into explicit obligations.

CONSTRAINTS (ABSOLUTE):
- Purely declarative
- No thresholds or fuzzy logic
- Binary conditions only
- Deterministic
- Does NOT alter generation
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homllm.intelligence.reasoning_contracts.interfaces import (
    ReasoningStep,
    ContractSeverity,
    Constraint,
    ReasoningContract,
)

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact
    from homllm.intelligence.reasoning_diagnostic import ReasoningDiagnosticResult
    from homllm.intelligence.assertion_readability import ReadabilityResult


class ContractBuilder:
    """
    Builds reasoning contracts from diagnostic results.
    
    Contract Construction Rules (Binary, No Thresholds):
    - ENUMERATION_REQUIRED: aggregation_expected AND readable >= 2
    - INTERACTION_REQUIRED: interaction_expected AND components >= 2
    - TRACE_REQUIRED: trace_expected
    - COMPLETENESS_REQUIRED: (enum OR interaction) AND readable > 0
    """
    
    def build(
        self,
        diagnostic_result: "ReasoningDiagnosticResult",
        readability_result: "ReadabilityResult",
        context: "ContextArtifact",
    ) -> ReasoningContract:
        """
        Build a reasoning contract from diagnostic results.
        
        Args:
            diagnostic_result: Result from Phase-1 RDL evaluation
            readability_result: Result from ARM evaluation
            context: Original ContextArtifact
            
        Returns:
            ReasoningContract with required steps and constraints.
        """
        constraints: list[Constraint] = []
        required_steps: list[ReasoningStep] = []
        
        expectations = diagnostic_result.expectations
        evidence = diagnostic_result.evidence
        readable_count = readability_result.readable_count
        
        # Rule 1: ENUMERATION_REQUIRED
        if expectations.aggregation_expected and readable_count >= 2:
            step = ReasoningStep.ENUMERATION_REQUIRED
            required_steps.append(step)
            constraints.append(Constraint(
                step=step,
                reason="Query requires enumeration of multiple items",
                evidence_count=readable_count,
            ))
        
        # Rule 2: INTERACTION_REQUIRED
        if expectations.interaction_expected and evidence.distinct_components_detected >= 2:
            step = ReasoningStep.INTERACTION_REQUIRED
            required_steps.append(step)
            constraints.append(Constraint(
                step=step,
                reason="Query requires explaining interaction between components",
                evidence_count=evidence.distinct_components_detected,
            ))
        
        # Rule 3: TRACE_REQUIRED
        if expectations.trace_expected:
            step = ReasoningStep.TRACE_REQUIRED
            required_steps.append(step)
            constraints.append(Constraint(
                step=step,
                reason="Query requires execution flow tracing",
                evidence_count=readable_count,
            ))
        
        # Rule 4: COMPLETENESS_REQUIRED
        # Emit if enum or interaction required AND readable blocks exist
        has_enum = ReasoningStep.ENUMERATION_REQUIRED in required_steps
        has_interaction = ReasoningStep.INTERACTION_REQUIRED in required_steps
        
        if (has_enum or has_interaction) and readable_count > 0:
            step = ReasoningStep.COMPLETENESS_REQUIRED
            required_steps.append(step)
            constraints.append(Constraint(
                step=step,
                reason="Query requires complete coverage of available context",
                evidence_count=readable_count,
            ))
        
        # Determine severity
        severity = ContractSeverity.REQUIRED if required_steps else ContractSeverity.ADVISORY
        
        return ReasoningContract(
            required_steps=tuple(required_steps),
            constraints=tuple(constraints),
            severity=severity,
        )


def create_contract_builder() -> ContractBuilder:
    """Factory function to create builder."""
    return ContractBuilder()


__all__ = [
    "ContractBuilder",
    "create_contract_builder",
]
