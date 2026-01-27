"""
Unit tests for Phase-3C: Prompt Integrity + Completion Guard

Tests:
1. Prompt variable injection occurs exactly once
2. No missing template variables
3. Completion Guard triggers when all required sections are present
4. No duplicate section headers allowed
5. Zero behavior change when flags are disabled
6. Regression tests pass unchanged

CONSTRAINTS:
- Tests are deterministic
- Tests verify zero side effects when disabled
- Tests verify no modification of intelligence logic
"""

import pytest

from homllm.intelligence.reasoning_contracts import (
    ReasoningContract,
    ReasoningStep,
    ContractSeverity,
    Constraint,
    # Phase-3C
    REQUIRED_TEMPLATE_VARIABLES,
    COMPLETION_GUARD_TEMPLATE,
    SECTION_HEADERS,
    PromptIntegrityGuard,
    create_prompt_integrity_guard,
    CompletionGuard,
    create_completion_guard,
    DeduplicationGuard,
    create_deduplication_guard,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def prompt_guard():
    """Create PromptIntegrityGuard instance."""
    return create_prompt_integrity_guard()


@pytest.fixture
def completion_guard():
    """Create CompletionGuard instance."""
    return create_completion_guard()


@pytest.fixture
def dedup_guard():
    """Create DeduplicationGuard instance."""
    return create_deduplication_guard()


@pytest.fixture
def empty_contract():
    """Create empty contract with no requirements."""
    return ReasoningContract.empty()


@pytest.fixture
def enumeration_contract():
    """Create contract with ENUMERATION_REQUIRED."""
    return ReasoningContract(
        required_steps=(ReasoningStep.ENUMERATION_REQUIRED,),
        constraints=(
            Constraint(
                step=ReasoningStep.ENUMERATION_REQUIRED,
                reason="Query requires enumeration",
                evidence_count=5,
            ),
        ),
        severity=ContractSeverity.REQUIRED,
    )


@pytest.fixture
def full_contract():
    """Create contract with all reasoning steps."""
    return ReasoningContract(
        required_steps=(
            ReasoningStep.ENUMERATION_REQUIRED,
            ReasoningStep.INTERACTION_REQUIRED,
            ReasoningStep.TRACE_REQUIRED,
            ReasoningStep.COMPLETENESS_REQUIRED,
        ),
        constraints=(
            Constraint(
                step=ReasoningStep.ENUMERATION_REQUIRED,
                reason="Enumeration required",
                evidence_count=5,
            ),
            Constraint(
                step=ReasoningStep.INTERACTION_REQUIRED,
                reason="Interaction required",
                evidence_count=3,
            ),
            Constraint(
                step=ReasoningStep.TRACE_REQUIRED,
                reason="Trace required",
                evidence_count=2,
            ),
            Constraint(
                step=ReasoningStep.COMPLETENESS_REQUIRED,
                reason="Completeness required",
                evidence_count=1,
            ),
        ),
        severity=ContractSeverity.REQUIRED,
    )


# =============================================================================
# PROMPT INTEGRITY GUARD TESTS
# =============================================================================

class TestPromptIntegrityGuard:
    """Tests for PromptIntegrityGuard (Phase-3C Problem 1 Fix)."""
    
    def test_required_variables_constant_exists(self):
        """Verify REQUIRED_TEMPLATE_VARIABLES constant is defined."""
        assert REQUIRED_TEMPLATE_VARIABLES is not None
        assert isinstance(REQUIRED_TEMPLATE_VARIABLES, frozenset)
        assert len(REQUIRED_TEMPLATE_VARIABLES) > 0
    
    def test_required_variables_includes_all_needed(self):
        """Verify all required template variables are in the constant."""
        assert "reasoning_enforcement" in REQUIRED_TEMPLATE_VARIABLES
        assert "structure_requirements" in REQUIRED_TEMPLATE_VARIABLES
        assert "completion_guard" in REQUIRED_TEMPLATE_VARIABLES
    
    def test_validate_and_fill_empty_dict(self, prompt_guard):
        """Filling empty dict should add all required variables."""
        result = prompt_guard.validate_and_fill({})
        
        for var_name in REQUIRED_TEMPLATE_VARIABLES:
            assert var_name in result
            assert result[var_name] == ""
    
    def test_validate_and_fill_preserves_existing(self, prompt_guard):
        """Existing variables should NOT be modified."""
        existing = {
            "reasoning_enforcement": "EXISTING_VALUE",
            "structure_requirements": "",
            "completion_guard": "ANOTHER_VALUE",
        }
        
        result = prompt_guard.validate_and_fill(existing)
        
        assert result["reasoning_enforcement"] == "EXISTING_VALUE"
        assert result["structure_requirements"] == ""
        assert result["completion_guard"] == "ANOTHER_VALUE"
    
    def test_validate_and_fill_partial(self, prompt_guard):
        """Partially filled dict should have missing vars added."""
        partial = {"reasoning_enforcement": "VALUE"}
        
        result = prompt_guard.validate_and_fill(partial)
        
        assert result["reasoning_enforcement"] == "VALUE"
        assert result["structure_requirements"] == ""
        assert result["completion_guard"] == ""
    
    def test_validate_and_fill_extra_vars_preserved(self, prompt_guard):
        """Extra variables not in required set should be preserved."""
        with_extra = {
            "reasoning_enforcement": "",
            "structure_requirements": "",
            "completion_guard": "",
            "extra_var": "EXTRA_VALUE",
        }
        
        result = prompt_guard.validate_and_fill(with_extra)
        
        assert result["extra_var"] == "EXTRA_VALUE"
    
    def test_validate_and_fill_no_double_injection(self, prompt_guard):
        """Variables should never be injected twice."""
        template_vars = {"reasoning_enforcement": "ONCE"}
        
        # First fill
        result1 = prompt_guard.validate_and_fill(template_vars)
        
        # Second fill (should be idempotent)
        result2 = prompt_guard.validate_and_fill(result1)
        
        assert result1 == result2
        assert result2["reasoning_enforcement"] == "ONCE"
    
    def test_assert_integrity_passes_when_complete(self, prompt_guard):
        """Assert should pass when all required variables exist."""
        complete = {
            "reasoning_enforcement": "",
            "structure_requirements": "",
            "completion_guard": "",
        }
        
        # Should not raise
        prompt_guard.assert_integrity(complete)
    
    def test_assert_integrity_fails_when_missing(self, prompt_guard):
        """Assert should fail when required variable is missing."""
        incomplete = {"reasoning_enforcement": ""}
        
        with pytest.raises(AssertionError) as exc_info:
            prompt_guard.assert_integrity(incomplete)
        
        assert "PROMPT_INTEGRITY_VIOLATION" in str(exc_info.value)
    
    def test_assert_integrity_error_message_contains_var_name(self, prompt_guard):
        """Error message should identify which variable is missing."""
        incomplete = {
            "reasoning_enforcement": "",
            # structure_requirements missing
            "completion_guard": "",
        }
        
        with pytest.raises(AssertionError) as exc_info:
            prompt_guard.assert_integrity(incomplete)
        
        assert "structure_requirements" in str(exc_info.value)


# =============================================================================
# COMPLETION GUARD TESTS
# =============================================================================

class TestCompletionGuard:
    """Tests for CompletionGuard (Phase-3C Problem 3 Fix)."""
    
    def test_empty_contract_returns_empty_string(self, completion_guard, empty_contract):
        """Empty contract should return empty string (zero side effects)."""
        result = completion_guard.render(empty_contract)
        assert result == ""
    
    def test_enumeration_contract_includes_section(self, completion_guard, enumeration_contract):
        """Enumeration contract should include correct section header."""
        result = completion_guard.render(enumeration_contract)
        
        assert "## Enumerated Components" in result
    
    def test_full_contract_includes_all_sections(self, completion_guard, full_contract):
        """Full contract should include all section headers."""
        result = completion_guard.render(full_contract)
        
        assert "## Enumerated Components" in result
        assert "## Component Interactions" in result
        assert "## Execution Trace" in result
        assert "## Summary" in result
    
    def test_render_includes_stop_instructions(self, completion_guard, enumeration_contract):
        """Rendered prompt should include stop instructions."""
        result = completion_guard.render(enumeration_contract)
        
        assert "stop generating" in result.lower() or "do not add" in result.lower()
        assert "End your response" in result or "end of your response" in result.lower()
    
    def test_render_includes_no_repeat_rule(self, completion_guard, enumeration_contract):
        """Rendered prompt should prohibit repeating section headers."""
        result = completion_guard.render(enumeration_contract)
        
        assert "repeat" in result.lower()
    
    def test_get_required_sections_empty_contract(self, completion_guard, empty_contract):
        """Empty contract should return empty tuple of sections."""
        result = completion_guard.get_required_sections(empty_contract)
        assert result == ()
    
    def test_get_required_sections_full_contract(self, completion_guard, full_contract):
        """Full contract should return all section headers in order."""
        result = completion_guard.get_required_sections(full_contract)
        
        assert len(result) == 4
        assert "## Enumerated Components" in result
        assert "## Component Interactions" in result
        assert "## Execution Trace" in result
        assert "## Summary" in result
    
    def test_deterministic_output(self, completion_guard, full_contract):
        """Same input should always produce same output."""
        result1 = completion_guard.render(full_contract)
        result2 = completion_guard.render(full_contract)
        
        assert result1 == result2
    
    def test_sections_numbered_list(self, completion_guard, full_contract):
        """Sections should be formatted as numbered list."""
        result = completion_guard.render(full_contract)
        
        assert "1." in result
        assert "2." in result


# =============================================================================
# DEDUPLICATION GUARD TESTS
# =============================================================================

class TestDeduplicationGuard:
    """Tests for DeduplicationGuard (Phase-3C Problem 2 Fix)."""
    
    def test_no_duplicates_in_clean_text(self, dedup_guard, full_contract):
        """Clean text with no duplicates should return empty list."""
        text = """
        ## Enumerated Components
        Component 1, Component 2
        
        ## Component Interactions
        They interact via APIs
        
        ## Execution Trace
        Step 1 -> Step 2
        
        ## Summary
        Everything works.
        """
        
        duplicates = dedup_guard.check_duplicates(text, full_contract)
        assert duplicates == []
    
    def test_detects_single_duplicate(self, dedup_guard, full_contract):
        """Should detect when a section header appears twice."""
        text = """
        ## Enumerated Components
        Component 1
        
        ## Enumerated Components
        Component 2 (duplicate!)
        
        ## Summary
        Done.
        """
        
        duplicates = dedup_guard.check_duplicates(text, full_contract)
        assert "## Enumerated Components" in duplicates
        assert len(duplicates) == 1
    
    def test_detects_multiple_duplicates(self, dedup_guard, full_contract):
        """Should detect multiple duplicated section headers."""
        text = """
        ## Enumerated Components
        First
        
        ## Enumerated Components
        Second
        
        ## Summary
        First summary
        
        ## Summary
        Second summary
        """
        
        duplicates = dedup_guard.check_duplicates(text, full_contract)
        assert "## Enumerated Components" in duplicates
        assert "## Summary" in duplicates
        assert len(duplicates) == 2
    
    def test_empty_contract_returns_no_duplicates(self, dedup_guard, empty_contract):
        """Empty contract should return no duplicates (zero side effects)."""
        text = "## Random Header\n## Random Header"
        
        duplicates = dedup_guard.check_duplicates(text, empty_contract)
        assert duplicates == []
    
    def test_all_sections_present_true(self, dedup_guard, full_contract):
        """Should return True when all required sections are present."""
        text = """
        ## Enumerated Components
        ## Component Interactions
        ## Execution Trace
        ## Summary
        """
        
        assert dedup_guard.all_sections_present(text, full_contract) is True
    
    def test_all_sections_present_false(self, dedup_guard, full_contract):
        """Should return False when any required section is missing."""
        text = """
        ## Enumerated Components
        ## Component Interactions
        # Missing Execution Trace and Summary
        """
        
        assert dedup_guard.all_sections_present(text, full_contract) is False
    
    def test_all_sections_present_empty_contract(self, dedup_guard, empty_contract):
        """Empty contract should return True (no requirements)."""
        text = "Random text without sections"
        
        assert dedup_guard.all_sections_present(text, empty_contract) is True
    
    def test_get_missing_sections(self, dedup_guard, full_contract):
        """Should return list of missing section headers."""
        text = """
        ## Enumerated Components
        Content
        """
        
        missing = dedup_guard.get_missing_sections(text, full_contract)
        
        assert "## Component Interactions" in missing
        assert "## Execution Trace" in missing
        assert "## Summary" in missing
        assert "## Enumerated Components" not in missing
    
    def test_get_missing_sections_empty_contract(self, dedup_guard, empty_contract):
        """Empty contract should return empty list (no requirements)."""
        missing = dedup_guard.get_missing_sections("any text", empty_contract)
        assert missing == []


# =============================================================================
# ZERO SIDE EFFECTS TESTS
# =============================================================================

class TestZeroSideEffects:
    """Tests verifying zero side effects when disabled."""
    
    def test_prompt_guard_disabled_returns_empty(self, prompt_guard):
        """With empty input and disabled flag, should return minimal dict."""
        result = prompt_guard.validate_and_fill({}, reasoning_enabled=False)
        
        # All required vars exist but are empty
        for var_name in REQUIRED_TEMPLATE_VARIABLES:
            assert var_name in result
            assert result[var_name] == ""
    
    def test_completion_guard_disabled_returns_empty(self, completion_guard, empty_contract):
        """Empty contract should produce no completion guard."""
        result = completion_guard.render(empty_contract)
        assert result == ""
    
    def test_dedup_guard_disabled_returns_empty(self, dedup_guard, empty_contract):
        """Empty contract should produce no duplicate warnings."""
        result = dedup_guard.check_duplicates("text", empty_contract)
        assert result == []


# =============================================================================
# SECTION HEADERS CONSTANT TESTS
# =============================================================================

class TestSectionHeaders:
    """Tests for SECTION_HEADERS constant."""
    
    def test_section_headers_constant_exists(self):
        """SECTION_HEADERS constant should be defined."""
        assert SECTION_HEADERS is not None
        assert isinstance(SECTION_HEADERS, dict)
    
    def test_section_headers_maps_all_steps(self):
        """SECTION_HEADERS should map all reasoning steps."""
        assert ReasoningStep.ENUMERATION_REQUIRED in SECTION_HEADERS
        assert ReasoningStep.INTERACTION_REQUIRED in SECTION_HEADERS
        assert ReasoningStep.TRACE_REQUIRED in SECTION_HEADERS
        assert ReasoningStep.COMPLETENESS_REQUIRED in SECTION_HEADERS
    
    def test_section_headers_use_markdown_format(self):
        """All section headers should use ## markdown format."""
        for step, header in SECTION_HEADERS.items():
            assert header.startswith("## "), f"{step} header should start with '## '"


# =============================================================================
# TEMPLATE CONSTANT TESTS
# =============================================================================

class TestCompletionGuardTemplate:
    """Tests for COMPLETION_GUARD_TEMPLATE constant."""
    
    def test_template_constant_exists(self):
        """COMPLETION_GUARD_TEMPLATE should be defined."""
        assert COMPLETION_GUARD_TEMPLATE is not None
        assert isinstance(COMPLETION_GUARD_TEMPLATE, str)
    
    def test_template_has_required_sections_placeholder(self):
        """Template should have placeholder for required sections."""
        assert "{required_sections}" in COMPLETION_GUARD_TEMPLATE
    
    def test_template_includes_stop_rules(self):
        """Template should include rules about stopping."""
        template_lower = COMPLETION_GUARD_TEMPLATE.lower()
        assert "stop" in template_lower or "end" in template_lower
        assert "repeat" in template_lower


# =============================================================================
# FACTORY FUNCTION TESTS
# =============================================================================

class TestFactoryFunctions:
    """Tests for factory functions."""
    
    def test_create_prompt_integrity_guard(self):
        """Factory should create PromptIntegrityGuard."""
        guard = create_prompt_integrity_guard()
        assert isinstance(guard, PromptIntegrityGuard)
    
    def test_create_completion_guard(self):
        """Factory should create CompletionGuard."""
        guard = create_completion_guard()
        assert isinstance(guard, CompletionGuard)
    
    def test_create_deduplication_guard(self):
        """Factory should create DeduplicationGuard."""
        guard = create_deduplication_guard()
        assert isinstance(guard, DeduplicationGuard)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestPhase3CIntegration:
    """Integration tests for Phase-3C workflow."""
    
    def test_full_workflow_with_contract(
        self, prompt_guard, completion_guard, dedup_guard, full_contract
    ):
        """Test complete Phase-3C workflow with active contract."""
        # Step 1: Render completion guard
        guard_prompt = completion_guard.render(full_contract)
        assert guard_prompt != ""
        
        # Step 2: Assemble template variables
        template_vars = {
            "reasoning_enforcement": "MOCK_ENFORCEMENT",
            "structure_requirements": "MOCK_STRUCTURE",
            "completion_guard": guard_prompt,
        }
        
        # Step 3: Validate and fill
        validated = prompt_guard.validate_and_fill(template_vars)
        
        # Step 4: Assert integrity
        prompt_guard.assert_integrity(validated)  # Should not raise
        
        # Step 5: Simulate generation (mock)
        generated_text = """
        ## Enumerated Components
        Component A and B
        
        ## Component Interactions
        A calls B
        
        ## Execution Trace
        1. A starts
        2. B responds
        
        ## Summary
        System works.
        """
        
        # Step 6: Check for duplicates
        duplicates = dedup_guard.check_duplicates(generated_text, full_contract)
        assert duplicates == []
        
        # Step 7: Verify all sections present
        assert dedup_guard.all_sections_present(generated_text, full_contract)
    
    def test_full_workflow_disabled(
        self, prompt_guard, completion_guard, dedup_guard, empty_contract
    ):
        """Test Phase-3C workflow when disabled (zero side effects)."""
        # Step 1: Empty contract produces empty guard
        guard_prompt = completion_guard.render(empty_contract)
        assert guard_prompt == ""
        
        # Step 2: Assemble with empty values
        template_vars = {
            "reasoning_enforcement": "",
            "structure_requirements": "",
            "completion_guard": "",
        }
        
        # Step 3: Validate passes
        validated = prompt_guard.validate_and_fill(template_vars)
        prompt_guard.assert_integrity(validated)
        
        # All values should be empty
        for var in REQUIRED_TEMPLATE_VARIABLES:
            assert validated[var] == ""
