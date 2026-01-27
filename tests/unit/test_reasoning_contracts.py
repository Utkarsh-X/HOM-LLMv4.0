"""
Unit tests for Reasoning Contract Layer (RCL).

Tests:
1. Correct contract emission for enumerative queries
2. Correct contract emission for interactional queries
3. No false positives when expectations don't exist
4. Deterministic output
5. Empty result when disabled
"""

import pytest
from unittest.mock import Mock


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_context():
    """Create mock ContextArtifact for testing."""
    from homllm.context.interfaces import ContextArtifact, ContextBlock
    
    return ContextArtifact(
        query_id="test_query",
        context_text="def test(): pass",
        blocks=(
            ContextBlock(
                block_id="block_1",
                file="component_a.py",
                start_line=1,
                end_line=5,
                content="def test(): pass",
                symbol_id="test",
                symbol_name="test",
                provenance=("retrieval",),
            ),
            ContextBlock(
                block_id="block_2",
                file="component_b.py",
                start_line=1,
                end_line=10,
                content="def helper(): return 42",
                symbol_id="helper",
                symbol_name="helper",
                provenance=("retrieval",),
            ),
        ),
        token_budget=4000,
        used_tokens=20,
        provenance={},
        explain_trace=(),
    )


@pytest.fixture
def mock_readability_result():
    """Create mock ReadabilityResult for testing."""
    from homllm.intelligence.assertion_readability import ReadabilityResult
    
    def _create(readable_count: int = 2):
        return ReadabilityResult(
            total_blocks=readable_count,
            readable_count=readable_count,
            suppressed_count=0,
            protected_but_readable_count=readable_count,
            entries=(),
        )
    
    return _create


@pytest.fixture
def mock_diagnostic_result():
    """Create mock ReasoningDiagnosticResult for testing."""
    from homllm.intelligence.reasoning_diagnostic import (
        ReasoningDiagnosticResult,
        ReasoningExpectation,
        ReasoningFailure,
        EvidenceSummary,
        DiagnosticConfidence,
        QueryTypeFlag,
    )
    
    def _create(
        aggregation_expected: bool = False,
        interaction_expected: bool = False,
        trace_expected: bool = False,
        readable_blocks: int = 2,
        distinct_components: int = 2,
    ) -> ReasoningDiagnosticResult:
        flags = []
        if aggregation_expected:
            flags.append(QueryTypeFlag.ENUMERATIVE)
        if interaction_expected:
            flags.append(QueryTypeFlag.INTERACTIONAL)
        if trace_expected:
            flags.append(QueryTypeFlag.TRACE)
        
        return ReasoningDiagnosticResult(
            query_type_flags=tuple(flags),
            expectations=ReasoningExpectation(
                aggregation_expected=aggregation_expected,
                interaction_expected=interaction_expected,
                trace_expected=trace_expected,
            ),
            failures=ReasoningFailure(False, False, False),
            evidence=EvidenceSummary(
                readable_blocks=readable_blocks,
                distinct_components_detected=distinct_components,
                enumeration_markers_found=False,
                interaction_markers_found=False,
                surrender_phrases_found=False,
            ),
            confidence=DiagnosticConfidence.MODERATE,
        )
    
    return _create


# =============================================================================
# IMPORT TESTS
# =============================================================================

def test_rcl_module_imports_succeed():
    """Verify RCL module imports work correctly."""
    from homllm.intelligence.reasoning_contracts import (
        ContractBuilder,
        ContractCollector,
        ReasoningContract,
        ReasoningStep,
        ContractSeverity,
        Constraint,
        create_contract_collector,
    )
    
    assert ContractBuilder is not None
    assert ContractCollector is not None
    assert ReasoningContract is not None
    assert ReasoningStep is not None


# =============================================================================
# DISABLED COLLECTOR TESTS
# =============================================================================

def test_disabled_collector_returns_empty_contract(mock_context, mock_readability_result, mock_diagnostic_result):
    """Verify disabled collector returns empty ReasoningContract."""
    from homllm.intelligence.reasoning_contracts import ContractCollector, ReasoningContract
    
    collector = ContractCollector(enabled=False)
    
    result = collector.collect(
        diagnostic_result=mock_diagnostic_result(),
        readability_result=mock_readability_result(),
        context=mock_context,
    )
    
    assert result == ReasoningContract.empty()


def test_collector_disabled_by_default():
    """Verify collector is disabled by default."""
    from homllm.intelligence.reasoning_contracts import ContractCollector
    
    collector = ContractCollector()
    assert collector.enabled is False


# =============================================================================
# CONTRACT EMISSION TESTS
# =============================================================================

def test_enumeration_contract_emission(mock_context, mock_readability_result, mock_diagnostic_result):
    """Verify ENUMERATION_REQUIRED is emitted for enumerative queries."""
    from homllm.intelligence.reasoning_contracts import ContractCollector, ReasoningStep
    
    collector = ContractCollector(enabled=True)
    
    result = collector.collect(
        diagnostic_result=mock_diagnostic_result(
            aggregation_expected=True,
            readable_blocks=3,
        ),
        readability_result=mock_readability_result(readable_count=3),
        context=mock_context,
    )
    
    assert ReasoningStep.ENUMERATION_REQUIRED in result.required_steps
    assert result.has_requirements


def test_interaction_contract_emission(mock_context, mock_readability_result, mock_diagnostic_result):
    """Verify INTERACTION_REQUIRED is emitted for interactional queries."""
    from homllm.intelligence.reasoning_contracts import ContractCollector, ReasoningStep
    
    collector = ContractCollector(enabled=True)
    
    result = collector.collect(
        diagnostic_result=mock_diagnostic_result(
            interaction_expected=True,
            distinct_components=3,
        ),
        readability_result=mock_readability_result(),
        context=mock_context,
    )
    
    assert ReasoningStep.INTERACTION_REQUIRED in result.required_steps


def test_trace_contract_emission(mock_context, mock_readability_result, mock_diagnostic_result):
    """Verify TRACE_REQUIRED is emitted for trace queries."""
    from homllm.intelligence.reasoning_contracts import ContractCollector, ReasoningStep
    
    collector = ContractCollector(enabled=True)
    
    result = collector.collect(
        diagnostic_result=mock_diagnostic_result(trace_expected=True),
        readability_result=mock_readability_result(),
        context=mock_context,
    )
    
    assert ReasoningStep.TRACE_REQUIRED in result.required_steps


def test_completeness_contract_with_enumeration(mock_context, mock_readability_result, mock_diagnostic_result):
    """Verify COMPLETENESS_REQUIRED is emitted when enumeration is required."""
    from homllm.intelligence.reasoning_contracts import ContractCollector, ReasoningStep
    
    collector = ContractCollector(enabled=True)
    
    result = collector.collect(
        diagnostic_result=mock_diagnostic_result(
            aggregation_expected=True,
            readable_blocks=5,
        ),
        readability_result=mock_readability_result(readable_count=5),
        context=mock_context,
    )
    
    assert ReasoningStep.ENUMERATION_REQUIRED in result.required_steps
    assert ReasoningStep.COMPLETENESS_REQUIRED in result.required_steps


def test_no_enumeration_contract_without_readable_blocks(mock_context, mock_readability_result, mock_diagnostic_result):
    """Verify ENUMERATION_REQUIRED not emitted without sufficient readable blocks."""
    from homllm.intelligence.reasoning_contracts import ContractCollector, ReasoningStep
    
    collector = ContractCollector(enabled=True)
    
    result = collector.collect(
        diagnostic_result=mock_diagnostic_result(
            aggregation_expected=True,
            readable_blocks=1,  # Less than 2
        ),
        readability_result=mock_readability_result(readable_count=1),
        context=mock_context,
    )
    
    assert ReasoningStep.ENUMERATION_REQUIRED not in result.required_steps


def test_no_interaction_contract_without_components(mock_context, mock_readability_result, mock_diagnostic_result):
    """Verify INTERACTION_REQUIRED not emitted without sufficient components."""
    from homllm.intelligence.reasoning_contracts import ContractCollector, ReasoningStep
    
    collector = ContractCollector(enabled=True)
    
    result = collector.collect(
        diagnostic_result=mock_diagnostic_result(
            interaction_expected=True,
            distinct_components=1,  # Less than 2
        ),
        readability_result=mock_readability_result(),
        context=mock_context,
    )
    
    assert ReasoningStep.INTERACTION_REQUIRED not in result.required_steps


# =============================================================================
# NO FALSE POSITIVES
# =============================================================================

def test_no_contracts_without_expectations(mock_context, mock_readability_result, mock_diagnostic_result):
    """Verify no contracts emitted when no expectations exist."""
    from homllm.intelligence.reasoning_contracts import ContractCollector
    
    collector = ContractCollector(enabled=True)
    
    result = collector.collect(
        diagnostic_result=mock_diagnostic_result(
            aggregation_expected=False,
            interaction_expected=False,
            trace_expected=False,
        ),
        readability_result=mock_readability_result(),
        context=mock_context,
    )
    
    assert not result.has_requirements
    assert len(result.required_steps) == 0


# =============================================================================
# DETERMINISM TESTS
# =============================================================================

def test_builder_determinism(mock_context, mock_readability_result, mock_diagnostic_result):
    """Verify same input produces same output."""
    from homllm.intelligence.reasoning_contracts import ContractCollector
    
    collector = ContractCollector(enabled=True)
    
    diagnostic = mock_diagnostic_result(aggregation_expected=True, readable_blocks=5)
    readability = mock_readability_result(readable_count=5)
    
    result1 = collector.collect(
        diagnostic_result=diagnostic,
        readability_result=readability,
        context=mock_context,
    )
    
    result2 = collector.collect(
        diagnostic_result=diagnostic,
        readability_result=readability,
        context=mock_context,
    )
    
    assert result1.required_steps == result2.required_steps
    assert result1.severity == result2.severity


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================

def test_contract_to_dict(mock_context, mock_readability_result, mock_diagnostic_result):
    """Verify ReasoningContract can be serialized to dictionary."""
    from homllm.intelligence.reasoning_contracts import ContractCollector
    import json
    
    collector = ContractCollector(enabled=True)
    
    result = collector.collect(
        diagnostic_result=mock_diagnostic_result(
            aggregation_expected=True,
            interaction_expected=True,
            readable_blocks=5,
            distinct_components=3,
        ),
        readability_result=mock_readability_result(readable_count=5),
        context=mock_context,
    )
    
    result_dict = result.to_dict()
    
    # Should be JSON serializable
    json_str = json.dumps(result_dict)
    assert json_str
    
    # Should contain expected fields
    assert "required_steps" in result_dict
    assert "constraints" in result_dict
    assert "severity" in result_dict


def test_empty_contract_to_dict():
    """Verify empty ReasoningContract serializes correctly."""
    from homllm.intelligence.reasoning_contracts import ReasoningContract
    import json
    
    result = ReasoningContract.empty()
    result_dict = result.to_dict()
    
    json_str = json.dumps(result_dict)
    assert json_str
    
    assert result_dict["required_steps"] == []


# =============================================================================
# IMMUTABILITY TESTS
# =============================================================================

def test_contract_frozen():
    """Verify ReasoningContract is immutable."""
    from homllm.intelligence.reasoning_contracts import ReasoningContract
    
    contract = ReasoningContract.empty()
    
    with pytest.raises(Exception):
        contract.severity = "modified"


def test_constraint_frozen():
    """Verify Constraint is immutable."""
    from homllm.intelligence.reasoning_contracts import Constraint, ReasoningStep
    
    constraint = Constraint(
        step=ReasoningStep.ENUMERATION_REQUIRED,
        reason="test",
        evidence_count=5,
    )
    
    with pytest.raises(Exception):
        constraint.evidence_count = 10


# =============================================================================
# SEVERITY TESTS
# =============================================================================

def test_severity_required_when_contracts_exist(mock_context, mock_readability_result, mock_diagnostic_result):
    """Verify severity is REQUIRED when contracts exist."""
    from homllm.intelligence.reasoning_contracts import ContractCollector, ContractSeverity
    
    collector = ContractCollector(enabled=True)
    
    result = collector.collect(
        diagnostic_result=mock_diagnostic_result(aggregation_expected=True, readable_blocks=5),
        readability_result=mock_readability_result(readable_count=5),
        context=mock_context,
    )
    
    assert result.severity == ContractSeverity.REQUIRED


def test_severity_advisory_when_no_contracts(mock_context, mock_readability_result, mock_diagnostic_result):
    """Verify severity is ADVISORY when no contracts exist."""
    from homllm.intelligence.reasoning_contracts import ContractCollector, ContractSeverity
    
    collector = ContractCollector(enabled=True)
    
    result = collector.collect(
        diagnostic_result=mock_diagnostic_result(),  # No expectations
        readability_result=mock_readability_result(),
        context=mock_context,
    )
    
    assert result.severity == ContractSeverity.ADVISORY


# =============================================================================
# FACTORY FUNCTION TESTS
# =============================================================================

def test_factory_function_creates_collector():
    """Verify factory function creates valid collector."""
    from homllm.intelligence.reasoning_contracts import create_contract_collector
    
    collector = create_contract_collector(enabled=True)
    
    assert collector is not None
    assert collector.enabled is True


def test_factory_function_default_disabled():
    """Verify factory creates disabled collector by default."""
    from homllm.intelligence.reasoning_contracts import create_contract_collector
    
    collector = create_contract_collector()
    
    assert collector.enabled is False
