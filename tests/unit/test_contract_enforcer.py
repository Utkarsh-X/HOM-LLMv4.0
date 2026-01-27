"""
Unit tests for Contract Enforcer (Phase-3A) and Structure Enforcer (Phase-3B).

Tests:
1. Empty contract returns empty string (zero side effects)
2. All obligation types render correctly
3. Compliance and safety rules present
4. Section mapping correct (Phase-3B)
5. Deterministic output
"""

import pytest

from homllm.intelligence.reasoning_contracts import (
    ContractEnforcer,
    create_contract_enforcer,
    StructureEnforcer,
    create_structure_enforcer,
    ReasoningContract,
    ReasoningStep,
    ContractSeverity,
    Constraint,
    ENFORCEMENT_TEMPLATE,
    STRUCTURE_TEMPLATE,
    SECTION_MAPPING,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def enforcer():
    """Create ContractEnforcer instance."""
    return create_contract_enforcer()


@pytest.fixture
def structure_enforcer():
    """Create StructureEnforcer instance."""
    return create_structure_enforcer()


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
                reason="Query requires enumeration of multiple items",
                evidence_count=5,
            ),
        ),
        severity=ContractSeverity.REQUIRED,
    )


@pytest.fixture
def interaction_contract():
    """Create contract with INTERACTION_REQUIRED."""
    return ReasoningContract(
        required_steps=(ReasoningStep.INTERACTION_REQUIRED,),
        constraints=(
            Constraint(
                step=ReasoningStep.INTERACTION_REQUIRED,
                reason="Query requires explaining interaction between components",
                evidence_count=3,
            ),
        ),
        severity=ContractSeverity.REQUIRED,
    )


@pytest.fixture
def trace_contract():
    """Create contract with TRACE_REQUIRED."""
    return ReasoningContract(
        required_steps=(ReasoningStep.TRACE_REQUIRED,),
        constraints=(
            Constraint(
                step=ReasoningStep.TRACE_REQUIRED,
                reason="Query requires execution flow tracing",
                evidence_count=2,
            ),
        ),
        severity=ContractSeverity.REQUIRED,
    )


@pytest.fixture
def full_contract():
    """Create contract with all obligation types."""
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
                reason="Query requires enumeration",
                evidence_count=5,
            ),
            Constraint(
                step=ReasoningStep.INTERACTION_REQUIRED,
                reason="Query requires interaction",
                evidence_count=3,
            ),
            Constraint(
                step=ReasoningStep.TRACE_REQUIRED,
                reason="Query requires tracing",
                evidence_count=2,
            ),
            Constraint(
                step=ReasoningStep.COMPLETENESS_REQUIRED,
                reason="Query requires completeness",
                evidence_count=5,
            ),
        ),
        severity=ContractSeverity.REQUIRED,
    )


# =============================================================================
# PHASE-3A: ZERO SIDE EFFECTS TESTS
# =============================================================================

def test_empty_contract_returns_empty_string(enforcer, empty_contract):
    """Verify empty contract produces empty string (zero side effects)."""
    result = enforcer.render(empty_contract)
    
    assert result == ""


def test_no_requirements_returns_empty_string(enforcer):
    """Verify contract with no requirements returns empty string."""
    contract = ReasoningContract(
        required_steps=(),
        constraints=(),
        severity=ContractSeverity.ADVISORY,
    )
    
    result = enforcer.render(contract)
    
    assert result == ""


# =============================================================================
# PHASE-3A: OBLIGATION RENDERING TESTS
# =============================================================================

def test_enumeration_required_in_output(enforcer, enumeration_contract):
    """Verify ENUMERATION_REQUIRED appears in rendered text."""
    result = enforcer.render(enumeration_contract)
    
    assert "ENUMERATION_REQUIRED" in result


def test_interaction_required_in_output(enforcer, interaction_contract):
    """Verify INTERACTION_REQUIRED appears in rendered text."""
    result = enforcer.render(interaction_contract)
    
    assert "INTERACTION_REQUIRED" in result


def test_trace_required_in_output(enforcer, trace_contract):
    """Verify TRACE_REQUIRED appears in rendered text."""
    result = enforcer.render(trace_contract)
    
    assert "TRACE_REQUIRED" in result


def test_completeness_required_in_output(enforcer, full_contract):
    """Verify COMPLETENESS_REQUIRED appears in rendered text."""
    result = enforcer.render(full_contract)
    
    assert "COMPLETENESS_REQUIRED" in result


def test_multiple_obligations_rendered(enforcer, full_contract):
    """Verify all present obligations appear in output."""
    result = enforcer.render(full_contract)
    
    assert "ENUMERATION_REQUIRED" in result
    assert "INTERACTION_REQUIRED" in result
    assert "TRACE_REQUIRED" in result
    assert "COMPLETENESS_REQUIRED" in result


# =============================================================================
# PHASE-3A: COMPLIANCE RULES TESTS
# =============================================================================

def test_compliance_rules_present(enforcer, enumeration_contract):
    """Verify compliance rules section present in output."""
    result = enforcer.render(enumeration_contract)
    
    assert "Compliance Rules:" in result
    assert "explicitly list ALL required items" in result


def test_interaction_compliance_rule(enforcer, interaction_contract):
    """Verify interaction compliance rule present."""
    result = enforcer.render(interaction_contract)
    
    assert "explain how components interact" in result


def test_trace_compliance_rule(enforcer, trace_contract):
    """Verify trace compliance rule present."""
    result = enforcer.render(trace_contract)
    
    assert "describe execution order or flow" in result


def test_completeness_compliance_rule(enforcer, full_contract):
    """Verify completeness compliance rule present."""
    result = enforcer.render(full_contract)
    
    assert "partial or high-level answers are not acceptable" in result


# =============================================================================
# PHASE-3A: SAFETY RULES TESTS
# =============================================================================

def test_safety_rules_present(enforcer, enumeration_contract):
    """Verify safety rules section present in output."""
    result = enforcer.render(enumeration_contract)
    
    assert "Safety Rules:" in result


def test_no_invention_rule_present(enforcer, enumeration_contract):
    """Verify 'do not invent' safety rule present."""
    result = enforcer.render(enumeration_contract)
    
    assert "Do NOT invent components" in result


def test_missing_context_rule_present(enforcer, enumeration_contract):
    """Verify 'missing context' safety rule present."""
    result = enforcer.render(enumeration_contract)
    
    assert "If required information is missing" in result


def test_no_silent_omission_rule_present(enforcer, enumeration_contract):
    """Verify 'no silent omission' rule present."""
    result = enforcer.render(enumeration_contract)
    
    assert "Do NOT silently omit" in result


# =============================================================================
# PHASE-3A: STRUCTURE TESTS
# =============================================================================

def test_mandatory_header_present(enforcer, enumeration_contract):
    """Verify mandatory obligations header present."""
    result = enforcer.render(enumeration_contract)
    
    assert "mandatory" in result.lower()
    assert "must be satisfied explicitly" in result


def test_failure_warning_present(enforcer, enumeration_contract):
    """Verify failure warning present."""
    result = enforcer.render(enumeration_contract)
    
    assert "incomplete answer" in result


# =============================================================================
# PHASE-3A: DETERMINISM TESTS
# =============================================================================

def test_determinism(enforcer, full_contract):
    """Verify same contract produces same output."""
    result1 = enforcer.render(full_contract)
    result2 = enforcer.render(full_contract)
    
    assert result1 == result2


def test_factory_creates_valid_enforcer():
    """Verify factory function creates valid enforcer."""
    enforcer = create_contract_enforcer()
    
    assert enforcer is not None
    assert isinstance(enforcer, ContractEnforcer)


# =============================================================================
# PHASE-3A: TEMPLATE TESTS
# =============================================================================

def test_enforcement_template_exported():
    """Verify ENFORCEMENT_TEMPLATE is exported."""
    assert ENFORCEMENT_TEMPLATE is not None
    assert "Reasoning Obligations" in ENFORCEMENT_TEMPLATE
    assert "Compliance Rules" in ENFORCEMENT_TEMPLATE
    assert "Safety Rules" in ENFORCEMENT_TEMPLATE


# =============================================================================
# PHASE-3B: ZERO SIDE EFFECTS TESTS
# =============================================================================

def test_structure_empty_contract_returns_empty_string(structure_enforcer, empty_contract):
    """Verify empty contract produces empty string for structure (zero side effects)."""
    result = structure_enforcer.render(empty_contract)
    
    assert result == ""


def test_structure_no_requirements_returns_empty_string(structure_enforcer):
    """Verify contract with no requirements returns empty string for structure."""
    contract = ReasoningContract(
        required_steps=(),
        constraints=(),
        severity=ContractSeverity.ADVISORY,
    )
    
    result = structure_enforcer.render(contract)
    
    assert result == ""


# =============================================================================
# PHASE-3B: SECTION MAPPING TESTS
# =============================================================================

def test_enumeration_maps_to_enumerated_components(structure_enforcer, enumeration_contract):
    """Verify ENUMERATION_REQUIRED maps to ## Enumerated Components."""
    result = structure_enforcer.render(enumeration_contract)
    
    assert "## Enumerated Components" in result


def test_interaction_maps_to_component_interactions(structure_enforcer, interaction_contract):
    """Verify INTERACTION_REQUIRED maps to ## Component Interactions."""
    result = structure_enforcer.render(interaction_contract)
    
    assert "## Component Interactions" in result


def test_trace_maps_to_execution_trace(structure_enforcer, trace_contract):
    """Verify TRACE_REQUIRED maps to ## Execution Trace."""
    result = structure_enforcer.render(trace_contract)
    
    assert "## Execution Trace" in result


def test_completeness_maps_to_summary(structure_enforcer, full_contract):
    """Verify COMPLETENESS_REQUIRED maps to ## Summary."""
    result = structure_enforcer.render(full_contract)
    
    assert "## Summary" in result


def test_all_sections_rendered_for_full_contract(structure_enforcer, full_contract):
    """Verify all sections present for full contract."""
    result = structure_enforcer.render(full_contract)
    
    assert "## Enumerated Components" in result
    assert "## Component Interactions" in result
    assert "## Execution Trace" in result
    assert "## Summary" in result


# =============================================================================
# PHASE-3B: FORMATTING RULES TESTS
# =============================================================================

def test_structure_formatting_rules_present(structure_enforcer, enumeration_contract):
    """Verify formatting rules section present in output."""
    result = structure_enforcer.render(enumeration_contract)
    
    assert "Formatting Rules:" in result


def test_clear_section_headers_rule(structure_enforcer, enumeration_contract):
    """Verify 'clear section headers' rule present."""
    result = structure_enforcer.render(enumeration_contract)
    
    assert "clear section headers exactly as specified" in result


def test_substantive_content_rule(structure_enforcer, enumeration_contract):
    """Verify 'substantive content' rule present."""
    result = structure_enforcer.render(enumeration_contract)
    
    assert "must contain substantive content" in result


def test_no_merge_sections_rule(structure_enforcer, enumeration_contract):
    """Verify 'do not merge sections' rule present."""
    result = structure_enforcer.render(enumeration_contract)
    
    assert "Do NOT merge sections" in result


def test_no_prose_when_sections_rule(structure_enforcer, enumeration_contract):
    """Verify 'no prose when sections required' rule present."""
    result = structure_enforcer.render(enumeration_contract)
    
    assert "Do NOT answer purely in prose" in result


# =============================================================================
# PHASE-3B: DETERMINISM TESTS
# =============================================================================

def test_structure_determinism(structure_enforcer, full_contract):
    """Verify same contract produces same structure output."""
    result1 = structure_enforcer.render(full_contract)
    result2 = structure_enforcer.render(full_contract)
    
    assert result1 == result2


def test_structure_factory_creates_valid_enforcer():
    """Verify factory function creates valid structure enforcer."""
    enforcer = create_structure_enforcer()
    
    assert enforcer is not None
    assert isinstance(enforcer, StructureEnforcer)


# =============================================================================
# PHASE-3B: TEMPLATE AND MAPPING TESTS
# =============================================================================

def test_structure_template_exported():
    """Verify STRUCTURE_TEMPLATE is exported."""
    assert STRUCTURE_TEMPLATE is not None
    assert "Required Answer Structure" in STRUCTURE_TEMPLATE
    assert "Formatting Rules" in STRUCTURE_TEMPLATE


def test_section_mapping_exported():
    """Verify SECTION_MAPPING is exported and complete."""
    assert SECTION_MAPPING is not None
    assert ReasoningStep.ENUMERATION_REQUIRED in SECTION_MAPPING
    assert ReasoningStep.INTERACTION_REQUIRED in SECTION_MAPPING
    assert ReasoningStep.TRACE_REQUIRED in SECTION_MAPPING
    assert ReasoningStep.COMPLETENESS_REQUIRED in SECTION_MAPPING


def test_section_mapping_values_are_headers():
    """Verify section mapping values start with ##."""
    for step, section in SECTION_MAPPING.items():
        assert section.startswith("## "), f"Section for {step} should start with '## '"
