"""
Reasoning Contract Enforcer (Phase-3A + Phase-3B)

Phase-3A: Renders reasoning contracts into explicit prompt instructions.
Phase-3B: Renders required answer structure based on contracts.

CONSTRAINTS (ABSOLUTE):
- Pure declarative prompt generation
- No scoring, retries, or penalties
- Returns empty string when contract has no requirements
- Deterministic output
- Does NOT interpret meaning
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homllm.intelligence.reasoning_contracts.interfaces import ReasoningContract

from homllm.intelligence.reasoning_contracts.interfaces import ReasoningStep


# =============================================================================
# Phase-3A: Reasoning Obligations Enforcement
# =============================================================================

ENFORCEMENT_TEMPLATE = """
You must comply with the following reasoning obligations for this query.

These obligations are mandatory and must be satisfied explicitly in your answer.

Reasoning Obligations:
{reasoning_obligations}

Compliance Rules:
- If ENUMERATION_REQUIRED is present, you must explicitly list ALL required items.
- If INTERACTION_REQUIRED is present, you must explain how components interact, not just describe them individually.
- If TRACE_REQUIRED is present, you must describe execution order or flow.
- If COMPLETENESS_REQUIRED is present, partial or high-level answers are not acceptable.

Safety Rules:
- Do NOT invent components that are not present in the provided context.
- If required information is missing from the context, explicitly state that it is missing.
- Do NOT silently omit any required reasoning step.

Failure to satisfy these obligations will result in an incomplete answer.
"""


class ContractEnforcer:
    """
    Renders reasoning contracts into prompt enforcement text.
    
    This is pure declarative constraint projection:
    - No interpretation of meaning
    - No severity weighting
    - Binary presence only
    
    Returns empty string when contract has no requirements,
    ensuring zero side effects when disabled.
    """
    
    def render(self, contract: "ReasoningContract") -> str:
        """
        Render enforcement prompt from reasoning contract.
        
        Args:
            contract: ReasoningContract with required steps
            
        Returns:
            Enforcement prompt string.
            Empty string if contract has no requirements.
        """
        if not contract.has_requirements:
            return ""
        
        # Render obligations as simple newline-separated list
        # No interpretation, no severity weighting, binary presence only
        obligations = "\n".join(
            step.value.upper() for step in contract.required_steps
        )
        
        return ENFORCEMENT_TEMPLATE.format(reasoning_obligations=obligations).strip()


def create_contract_enforcer() -> ContractEnforcer:
    """Factory function to create enforcer."""
    return ContractEnforcer()


# =============================================================================
# Phase-3B: Structured Answer Enforcement
# =============================================================================

# Deterministic mapping: Contract → Required Section
SECTION_MAPPING = {
    ReasoningStep.ENUMERATION_REQUIRED: "## Enumerated Components",
    ReasoningStep.INTERACTION_REQUIRED: "## Component Interactions",
    ReasoningStep.TRACE_REQUIRED: "## Execution Trace",
    ReasoningStep.COMPLETENESS_REQUIRED: "## Summary",
}


STRUCTURE_TEMPLATE = """
You must structure your answer using the following sections.

Use ONLY the sections that are applicable based on the reasoning obligations.
Do NOT invent sections that are not required.

Required Answer Structure:
{structure_requirements}

Formatting Rules:
- Use clear section headers exactly as specified.
- Each required section must contain substantive content.
- Do NOT merge sections together.
- Do NOT answer purely in prose when sections are required.
"""


class StructureEnforcer:
    """
    Renders required answer structure based on reasoning contracts.
    
    Phase-3B: Format enforcement, not content enforcement.
    
    Deterministic mapping:
    - ENUMERATION_REQUIRED → ## Enumerated Components
    - INTERACTION_REQUIRED → ## Component Interactions
    - TRACE_REQUIRED → ## Execution Trace
    - COMPLETENESS_REQUIRED → ## Summary
    
    Returns empty string when contract has no requirements,
    ensuring zero side effects when disabled.
    """
    
    def render(self, contract: "ReasoningContract") -> str:
        """
        Render structure requirements from reasoning contract.
        
        Args:
            contract: ReasoningContract with required steps
            
        Returns:
            Structure requirements prompt string.
            Empty string if contract has no requirements.
        """
        if not contract.has_requirements:
            return ""
        
        # Build section list from contract steps (deterministic order)
        sections = []
        for step in contract.required_steps:
            if step in SECTION_MAPPING:
                sections.append(SECTION_MAPPING[step])
        
        if not sections:
            return ""
        
        structure_requirements = "\n".join(sections)
        
        return STRUCTURE_TEMPLATE.format(structure_requirements=structure_requirements).strip()


def create_structure_enforcer() -> StructureEnforcer:
    """Factory function to create structure enforcer."""
    return StructureEnforcer()


__all__ = [
    # Phase-3A
    "ContractEnforcer",
    "create_contract_enforcer",
    "ENFORCEMENT_TEMPLATE",
    # Phase-3B
    "StructureEnforcer",
    "create_structure_enforcer",
    "STRUCTURE_TEMPLATE",
    "SECTION_MAPPING",
]
