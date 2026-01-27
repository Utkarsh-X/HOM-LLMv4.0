"""
Unit tests for Reasoning Diagnostic Layer (RDL).

Tests:
1. Determinism (same input → same output)
2. Query type detection
3. Aggregation failure detection
4. Interaction failure detection
5. Premature surrender detection
6. Zero impact when disabled
7. JSON serialization stability
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


# =============================================================================
# IMPORT TESTS
# =============================================================================

def test_rdl_module_imports_succeed():
    """Verify RDL module imports work correctly."""
    from homllm.intelligence.reasoning_diagnostic import (
        ReasoningDiagnosticEvaluator,
        ReasoningDiagnosticResult,
        ReasoningDiagnosticCollector,
        QueryTypeFlag,
        DiagnosticConfidence,
        ReasoningExpectation,
        ReasoningFailure,
        EvidenceSummary,
        create_reasoning_collector,
    )
    
    assert ReasoningDiagnosticEvaluator is not None
    assert ReasoningDiagnosticResult is not None
    assert ReasoningDiagnosticCollector is not None
    assert QueryTypeFlag is not None


# =============================================================================
# DISABLED COLLECTOR TESTS
# =============================================================================

def test_disabled_collector_returns_empty_result(mock_context, mock_readability_result):
    """Verify disabled collector returns empty ReasoningDiagnosticResult."""
    from homllm.intelligence.reasoning_diagnostic import (
        ReasoningDiagnosticCollector,
        ReasoningDiagnosticResult,
    )
    
    collector = ReasoningDiagnosticCollector(enabled=False)
    
    result = collector.collect(
        query_text="test query",
        answer_text="test answer",
        readability_result=mock_readability_result(),
        context=mock_context,
    )
    
    assert result == ReasoningDiagnosticResult.empty()


def test_collector_disabled_by_default():
    """Verify collector is disabled by default."""
    from homllm.intelligence.reasoning_diagnostic import ReasoningDiagnosticCollector
    
    collector = ReasoningDiagnosticCollector()
    assert collector.enabled is False


# =============================================================================
# QUERY TYPE DETECTION TESTS
# =============================================================================

def test_enumerative_query_detection(mock_context, mock_readability_result):
    """Verify enumerative query is detected."""
    from homllm.intelligence.reasoning_diagnostic import (
        ReasoningDiagnosticCollector,
        QueryTypeFlag,
    )
    
    collector = ReasoningDiagnosticCollector(enabled=True)
    
    result = collector.collect(
        query_text="List all the optimization rules",
        answer_text="There are several rules.",
        readability_result=mock_readability_result(),
        context=mock_context,
    )
    
    assert QueryTypeFlag.ENUMERATIVE in result.query_type_flags
    assert result.expectations.aggregation_expected is True


def test_interactional_query_detection(mock_context, mock_readability_result):
    """Verify interactional query is detected."""
    from homllm.intelligence.reasoning_diagnostic import (
        ReasoningDiagnosticCollector,
        QueryTypeFlag,
    )
    
    collector = ReasoningDiagnosticCollector(enabled=True)
    
    result = collector.collect(
        query_text="How do component A and component B interact together?",
        answer_text="They work independently.",
        readability_result=mock_readability_result(),
        context=mock_context,
    )
    
    assert QueryTypeFlag.INTERACTIONAL in result.query_type_flags
    assert result.expectations.interaction_expected is True


def test_trace_query_detection(mock_context, mock_readability_result):
    """Verify trace query is detected."""
    from homllm.intelligence.reasoning_diagnostic import (
        ReasoningDiagnosticCollector,
        QueryTypeFlag,
    )
    
    collector = ReasoningDiagnosticCollector(enabled=True)
    
    result = collector.collect(
        query_text="Trace the execution flow of the request",
        answer_text="The request goes through several steps.",
        readability_result=mock_readability_result(),
        context=mock_context,
    )
    
    assert QueryTypeFlag.TRACE in result.query_type_flags
    assert result.expectations.trace_expected is True


# =============================================================================
# FAILURE DETECTION TESTS
# =============================================================================

def test_aggregation_missing_detected(mock_context, mock_readability_result):
    """Verify aggregation missing is detected when expected."""
    from homllm.intelligence.reasoning_diagnostic import ReasoningDiagnosticCollector
    
    collector = ReasoningDiagnosticCollector(enabled=True)
    
    # Query expects enumeration, answer doesn't provide it
    result = collector.collect(
        query_text="List all the rules in the system",
        answer_text="The system has rules.",  # No enumeration
        readability_result=mock_readability_result(readable_count=3),
        context=mock_context,
    )
    
    assert result.failures.aggregation_missing is True


def test_aggregation_not_missing_with_enumeration(mock_context, mock_readability_result):
    """Verify aggregation not flagged when answer enumerates."""
    from homllm.intelligence.reasoning_diagnostic import ReasoningDiagnosticCollector
    
    collector = ReasoningDiagnosticCollector(enabled=True)
    
    # Query expects enumeration, answer provides it
    result = collector.collect(
        query_text="List all the rules",
        answer_text="1. First rule\n2. Second rule\n3. Third rule",
        readability_result=mock_readability_result(readable_count=3),
        context=mock_context,
    )
    
    assert result.failures.aggregation_missing is False


def test_interaction_missing_detected(mock_context, mock_readability_result):
    """Verify interaction missing is detected."""
    from homllm.intelligence.reasoning_diagnostic import ReasoningDiagnosticCollector
    
    collector = ReasoningDiagnosticCollector(enabled=True)
    
    # Components exist but answer doesn't connect them
    result = collector.collect(
        query_text="Describe the components",
        answer_text="Component A exists. Component B exists.",  # No interaction
        readability_result=mock_readability_result(),
        context=mock_context,
    )
    
    assert result.failures.interaction_missing is True


def test_interaction_not_missing_with_connection(mock_context, mock_readability_result):
    """Verify interaction not flagged when answer connects components."""
    from homllm.intelligence.reasoning_diagnostic import ReasoningDiagnosticCollector
    
    collector = ReasoningDiagnosticCollector(enabled=True)
    
    # Answer connects components
    result = collector.collect(
        query_text="Describe the components",
        answer_text="Component A calls Component B, which then returns the result.",
        readability_result=mock_readability_result(),
        context=mock_context,
    )
    
    assert result.failures.interaction_missing is False


def test_premature_surrender_detected(mock_context, mock_readability_result):
    """Verify premature surrender is detected."""
    from homllm.intelligence.reasoning_diagnostic import ReasoningDiagnosticCollector
    
    collector = ReasoningDiagnosticCollector(enabled=True)
    
    # Answer claims not found despite readable context
    result = collector.collect(
        query_text="Describe the caching mechanism",
        answer_text="The caching mechanism is not in context.",
        readability_result=mock_readability_result(readable_count=5),
        context=mock_context,
    )
    
    assert result.failures.premature_surrender is True


def test_surrender_not_flagged_without_readable_context(mock_context, mock_readability_result):
    """Verify surrender not flagged when no readable context exists."""
    from homllm.intelligence.reasoning_diagnostic import ReasoningDiagnosticCollector
    
    collector = ReasoningDiagnosticCollector(enabled=True)
    
    # No readable context, so "not found" is legitimate
    result = collector.collect(
        query_text="Describe the caching mechanism",
        answer_text="The caching mechanism is not in context.",
        readability_result=mock_readability_result(readable_count=0),
        context=mock_context,
    )
    
    assert result.failures.premature_surrender is False


# =============================================================================
# DETERMINISM TESTS
# =============================================================================

def test_evaluator_determinism(mock_context, mock_readability_result):
    """Verify same input produces same output."""
    from homllm.intelligence.reasoning_diagnostic import ReasoningDiagnosticCollector
    
    collector = ReasoningDiagnosticCollector(enabled=True)
    
    result1 = collector.collect(
        query_text="List all rules",
        answer_text="Here are the rules.",
        readability_result=mock_readability_result(),
        context=mock_context,
    )
    
    result2 = collector.collect(
        query_text="List all rules",
        answer_text="Here are the rules.",
        readability_result=mock_readability_result(),
        context=mock_context,
    )
    
    assert result1.query_type_flags == result2.query_type_flags
    assert result1.failures == result2.failures
    assert result1.confidence == result2.confidence


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================

def test_diagnostic_result_to_dict(mock_context, mock_readability_result):
    """Verify ReasoningDiagnosticResult can be serialized to dictionary."""
    from homllm.intelligence.reasoning_diagnostic import ReasoningDiagnosticCollector
    import json
    
    collector = ReasoningDiagnosticCollector(enabled=True)
    
    result = collector.collect(
        query_text="List all rules",
        answer_text="Here are the rules.",
        readability_result=mock_readability_result(),
        context=mock_context,
    )
    
    result_dict = result.to_dict()
    
    # Should be JSON serializable
    json_str = json.dumps(result_dict)
    assert json_str
    
    # Should contain expected fields
    assert "query_type_flags" in result_dict
    assert "expectations" in result_dict
    assert "failures" in result_dict
    assert "evidence" in result_dict
    assert "confidence" in result_dict


def test_empty_diagnostic_result_to_dict():
    """Verify empty ReasoningDiagnosticResult serializes correctly."""
    from homllm.intelligence.reasoning_diagnostic import ReasoningDiagnosticResult
    import json
    
    result = ReasoningDiagnosticResult.empty()
    result_dict = result.to_dict()
    
    json_str = json.dumps(result_dict)
    assert json_str
    
    assert result_dict["failures"]["aggregation_missing"] is False
    assert result_dict["failures"]["interaction_missing"] is False
    assert result_dict["failures"]["premature_surrender"] is False


# =============================================================================
# IMMUTABILITY TESTS
# =============================================================================

def test_diagnostic_result_frozen():
    """Verify ReasoningDiagnosticResult is immutable."""
    from homllm.intelligence.reasoning_diagnostic import ReasoningDiagnosticResult
    
    result = ReasoningDiagnosticResult.empty()
    
    with pytest.raises(Exception):
        result.confidence = "modified"


def test_reasoning_failure_frozen():
    """Verify ReasoningFailure is immutable."""
    from homllm.intelligence.reasoning_diagnostic import ReasoningFailure
    
    failure = ReasoningFailure(
        aggregation_missing=False,
        interaction_missing=False,
        premature_surrender=False,
    )
    
    with pytest.raises(Exception):
        failure.aggregation_missing = True


# =============================================================================
# FACTORY FUNCTION TESTS
# =============================================================================

def test_factory_function_creates_collector():
    """Verify factory function creates valid collector."""
    from homllm.intelligence.reasoning_diagnostic import create_reasoning_collector
    
    collector = create_reasoning_collector(enabled=True)
    
    assert collector is not None
    assert collector.enabled is True


def test_factory_function_default_disabled():
    """Verify factory creates disabled collector by default."""
    from homllm.intelligence.reasoning_diagnostic import create_reasoning_collector
    
    collector = create_reasoning_collector()
    
    assert collector.enabled is False


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

def test_no_false_positives_without_expectations(mock_context, mock_readability_result):
    """Verify no failures flagged when no expectations exist."""
    from homllm.intelligence.reasoning_diagnostic import ReasoningDiagnosticCollector
    
    collector = ReasoningDiagnosticCollector(enabled=True)
    
    # Generic query with no specific expectations
    result = collector.collect(
        query_text="What is this file?",
        answer_text="This file contains code.",
        readability_result=mock_readability_result(readable_count=1),
        context=mock_context,
    )
    
    # No aggregation expected, so shouldn't flag aggregation missing
    assert result.failures.aggregation_missing is False
