"""
Phase-3C: Prompt Integrity + Completion Guard

Fixes three problems:
1. Prompt Injection Bug - Ensures template variables exist before rendering
2. Structural Duplication - Prevents duplicate section headers
3. No Completion Boundary - Injects stop instruction when obligations are met

CONSTRAINTS (ABSOLUTE):
- Pure declarative prompt generation
- No scoring, retries, or penalties
- Deterministic output
- Zero side effects when disabled
- Does NOT interpret meaning
- Does NOT modify model output content - only adds stopping instructions
"""

from __future__ import annotations

from typing import TYPE_CHECKING, FrozenSet

if TYPE_CHECKING:
    from homllm.intelligence.reasoning_contracts.interfaces import ReasoningContract

from homllm.intelligence.reasoning_contracts.interfaces import ReasoningStep

# =============================================================================
# Constants
# =============================================================================

# Required template variables that MUST exist before rendering
REQUIRED_TEMPLATE_VARIABLES: FrozenSet[str] = frozenset({
    "reasoning_enforcement",
    "structure_requirements",
    "completion_guard",
})


# Completion Guard template
# Injected after structure requirements to signal model when to stop
COMPLETION_GUARD_TEMPLATE = """
Completion Rules:
You must stop generating content after completing all required sections.

Required sections for this response:
{required_sections}

Once you have written content for ALL of the above sections:
1. Do NOT add additional sections or explanations
2. Do NOT repeat any section header
3. End your response immediately after the final required section

If you attempt to re-emit any section header that has already appeared,
treat this as the natural end of your response.
"""


# Deterministic mapping: Contract → Required Section Header
# Same as Phase-3B SECTION_MAPPING for consistency
SECTION_HEADERS = {
    ReasoningStep.ENUMERATION_REQUIRED: "## Enumerated Components",
    ReasoningStep.INTERACTION_REQUIRED: "## Component Interactions",
    ReasoningStep.TRACE_REQUIRED: "## Execution Trace",
    ReasoningStep.COMPLETENESS_REQUIRED: "## Summary",
}


# =============================================================================
# Prompt Injection Integrity
# =============================================================================

class PromptIntegrityGuard:
    """
    Ensures prompt template variables exist before rendering.
    
    Phase-3C Problem 1 Fix:
    - Guarantees all required variables exist (empty string if not set)
    - Validates no missing template variables
    - Prevents double injection
    
    Returns empty string when disabled (zero side effects).
    """
    
    def validate_and_fill(
        self,
        template_variables: dict,
        reasoning_enabled: bool = False,
    ) -> dict:
        """
        Validate and fill template variables.
        
        GUARANTEES:
        - All REQUIRED_TEMPLATE_VARIABLES will exist in returned dict
        - Missing variables are filled with empty string
        - Existing variables are NOT modified
        - No variable is injected twice
        
        Args:
            template_variables: Existing template variables dict
            reasoning_enabled: Whether reasoning contracts are enabled
            
        Returns:
            dict with all required variables guaranteed to exist
        """
        result = dict(template_variables)  # Shallow copy
        
        for var_name in REQUIRED_TEMPLATE_VARIABLES:
            if var_name not in result:
                # Fill missing with empty string
                # This ensures zero side effects when disabled
                result[var_name] = ""
        
        return result
    
    def assert_integrity(self, template_variables: dict) -> None:
        """
        Assert that all required template variables exist.
        
        Raises AssertionError if any required variable is missing.
        Use this in critical paths to catch injection bugs early.
        
        Args:
            template_variables: Template variables to validate
            
        Raises:
            AssertionError: If any required variable is missing
        """
        for var_name in REQUIRED_TEMPLATE_VARIABLES:
            assert var_name in template_variables, (
                f"PROMPT_INTEGRITY_VIOLATION: Missing template variable: '{var_name}'. "
                f"This indicates a prompt injection bug."
            )


def create_prompt_integrity_guard() -> PromptIntegrityGuard:
    """Factory function to create prompt integrity guard."""
    return PromptIntegrityGuard()


# =============================================================================
# Completion Guard
# =============================================================================

class CompletionGuard:
    """
    Injects stop instructions when all reasoning obligations are met.
    
    Phase-3C Problem 3 Fix:
    - Maps required contracts to required section headers
    - When all required sections are declared, injects stop instruction
    - Deterministic, no scoring, no retries, no penalties
    
    Returns empty string when disabled or no requirements (zero side effects).
    """
    
    def render(self, contract: "ReasoningContract") -> str:
        """
        Render completion guard prompt from reasoning contract.
        
        Args:
            contract: ReasoningContract with required steps
            
        Returns:
            Completion guard prompt string.
            Empty string if contract has no requirements.
        """
        if not contract.has_requirements:
            return ""
        
        # Build required sections list from contract steps
        required_sections = []
        for step in contract.required_steps:
            if step in SECTION_HEADERS:
                required_sections.append(SECTION_HEADERS[step])
        
        if not required_sections:
            return ""
        
        # Format as numbered list for clarity
        section_list = "\n".join(
            f"  {i+1}. {section}" 
            for i, section in enumerate(required_sections)
        )
        
        return COMPLETION_GUARD_TEMPLATE.format(
            required_sections=section_list
        ).strip()
    
    def get_required_sections(self, contract: "ReasoningContract") -> tuple[str, ...]:
        """
        Get tuple of required section headers from contract.
        
        Useful for deduplication checking.
        
        Args:
            contract: ReasoningContract with required steps
            
        Returns:
            Tuple of section header strings
        """
        if not contract.has_requirements:
            return ()
        
        return tuple(
            SECTION_HEADERS[step]
            for step in contract.required_steps
            if step in SECTION_HEADERS
        )


def create_completion_guard() -> CompletionGuard:
    """Factory function to create completion guard."""
    return CompletionGuard()


# =============================================================================
# Structure Deduplication Guard
# =============================================================================

class DeduplicationGuard:
    """
    Checks for and prevents duplicate section headers.
    
    Phase-3C Problem 2 Fix:
    - Tracks which sections have been emitted
    - Detects if same section appears twice
    - Deterministic, read-only analysis
    
    This is used for validation, not generation modification.
    """
    
    def check_duplicates(self, text: str, contract: "ReasoningContract") -> list[str]:
        """
        Check for duplicate section headers in generated text.
        
        Args:
            text: Generated response text
            contract: ReasoningContract with required steps
            
        Returns:
            List of section headers that appear more than once.
            Empty list if no duplicates.
        """
        if not contract.has_requirements:
            return []
        
        duplicates = []
        for step in contract.required_steps:
            if step in SECTION_HEADERS:
                header = SECTION_HEADERS[step]
                # Count occurrences of this section header
                count = text.count(header)
                if count > 1:
                    duplicates.append(header)
        
        return duplicates
    
    def all_sections_present(self, text: str, contract: "ReasoningContract") -> bool:
        """
        Check if all required sections are present in text.
        
        Args:
            text: Generated response text
            contract: ReasoningContract with required steps
            
        Returns:
            True if all required sections appear at least once
        """
        if not contract.has_requirements:
            return True
        
        for step in contract.required_steps:
            if step in SECTION_HEADERS:
                header = SECTION_HEADERS[step]
                if header not in text:
                    return False
        
        return True
    
    def get_missing_sections(self, text: str, contract: "ReasoningContract") -> list[str]:
        """
        Get list of required sections that are missing from text.
        
        Args:
            text: Generated response text
            contract: ReasoningContract with required steps
            
        Returns:
            List of section headers that are required but not present
        """
        if not contract.has_requirements:
            return []
        
        missing = []
        for step in contract.required_steps:
            if step in SECTION_HEADERS:
                header = SECTION_HEADERS[step]
                if header not in text:
                    missing.append(header)
        
        return missing


def create_deduplication_guard() -> DeduplicationGuard:
    """Factory function to create deduplication guard."""
    return DeduplicationGuard()


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Constants
    "REQUIRED_TEMPLATE_VARIABLES",
    "COMPLETION_GUARD_TEMPLATE",
    "SECTION_HEADERS",
    # Prompt Integrity
    "PromptIntegrityGuard",
    "create_prompt_integrity_guard",
    # Completion Guard
    "CompletionGuard",
    "create_completion_guard",
    # Deduplication Guard
    "DeduplicationGuard",
    "create_deduplication_guard",
]
