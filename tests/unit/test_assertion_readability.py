"""
Unit tests for Assertion Readability Model (ARM).

Tests:
1. Determinism (same input → same output)
2. Protected block with functions → READABLE
3. Fragmented block with low signal → NOT READABLE
4. Zero impact when disabled
5. JSON serialization stability
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
                file="test.py",
                start_line=1,
                end_line=5,
                content="def test(): pass",
                symbol_id="test",
                symbol_name="test",
                provenance=("retrieval",),
            ),
            ContextBlock(
                block_id="block_2",
                file="helper.py",
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
def mock_block_diagnostic():
    """Create a mock IntraBlockDiagnostic for testing."""
    from homllm.intelligence.diagnostics.inspect_context import (
        IntraBlockDiagnostic,
        TokenBreakdown,
        IdentifierDensity,
        StructuralPayload,
        RedundancyHints,
    )
    
    def _create(
        block_id: str = "block_1",
        function_count: int = 1,
        class_count: int = 0,
        method_count: int = 0,
        decorator_count: int = 0,
        control_flow_lines: int = 2,
        code_lines: int = 10,
        signature_lines: int = 1,
        signal_ratio: float = 0.7,
        noise_ratio: float = 0.2,
    ) -> IntraBlockDiagnostic:
        return IntraBlockDiagnostic(
            block_id=block_id,
            file="test.py",
            symbol="test_function",
            tokens=100,
            token_breakdown=TokenBreakdown(
                logging_pct=5.0,
                docstrings_pct=10.0,
                control_flow_lines=control_flow_lines,
                code_lines=code_lines,
                signature_lines=signature_lines,
            ),
            identifier_density=IdentifierDensity(),
            structural_payload=StructuralPayload(
                function_count=function_count,
                class_count=class_count,
                method_count=method_count,
                decorator_count=decorator_count,
            ),
            redundancy_hints=RedundancyHints(
                boilerplate_score=0.2,
            ),
            signal_ratio=signal_ratio,
            noise_ratio=noise_ratio,
        )
    
    return _create


@pytest.fixture
def mock_diagnostics(mock_block_diagnostic):
    """Create mock DiagnosticSnapshot for testing."""
    from homllm.intelligence.interfaces import (
        DiagnosticSnapshot,
        StructuralDiagnostics,
        SemanticDiagnostics,
        CognitiveDiagnostics,
    )
    
    def _create(blocks=None):
        if blocks is None:
            blocks = (
                mock_block_diagnostic(block_id="block_1", function_count=1),
                mock_block_diagnostic(block_id="block_2", function_count=1),
            )
        
        return DiagnosticSnapshot(
            level1=StructuralDiagnostics(
                status="available",
                reason="",
                blocks=blocks,
                result=None,
            ),
            level2=SemanticDiagnostics(
                status="available",
                reason="",
                result=None,
            ),
            level3=CognitiveDiagnostics(
                status="available",
                reason="",
                result=None,
            ),
        )
    
    return _create


@pytest.fixture
def mock_modification_plan():
    """Create mock ContextModificationPlan for testing."""
    from homllm.intelligence.controller import (
        ContextModificationPlan,
        UnifiedAction,
    )
    from homllm.intelligence.actions.level1.plan import (
        ContextModificationPlan as L1Plan,
    )
    from homllm.intelligence.actions.level2.plan import SemanticActionPlan
    from homllm.intelligence.actions.level3.plan import CognitiveActionPlan
    
    def _create(unified_actions=None):
        if unified_actions is None:
            unified_actions = ()
        
        return ContextModificationPlan(
            level1_plan=L1Plan.empty(),
            level2_plan=SemanticActionPlan.empty(),
            level3_plan=CognitiveActionPlan.empty(),
            unified_actions=unified_actions,
            diagnostics_available=True,
            levels_executed=(1, 2, 3),
            total_actions=len(unified_actions),
        )
    
    return _create


# =============================================================================
# IMPORT TESTS
# =============================================================================

def test_arm_module_imports_succeed():
    """Verify ARM module imports work correctly."""
    from homllm.intelligence.assertion_readability import (
        AssertionReadabilityEvaluator,
        ReadabilityResult,
        AssertionReadability,
        ReadabilityReason,
        ReadabilityCollector,
        create_readability_collector,
    )
    
    assert AssertionReadabilityEvaluator is not None
    assert ReadabilityResult is not None
    assert AssertionReadability is not None
    assert ReadabilityReason is not None
    assert ReadabilityCollector is not None
    assert create_readability_collector is not None


# =============================================================================
# DISABLED COLLECTOR TESTS
# =============================================================================

def test_disabled_collector_returns_empty_result(mock_context, mock_diagnostics, mock_modification_plan):
    """Verify disabled collector returns empty ReadabilityResult."""
    from homllm.intelligence.assertion_readability import ReadabilityCollector, ReadabilityResult
    
    collector = ReadabilityCollector(enabled=False)
    
    result = collector.collect(
        mock_diagnostics(),
        mock_modification_plan(),
        mock_context,
    )
    
    assert result.total_blocks == 0
    assert result.readable_count == 0
    assert result.suppressed_count == 0
    assert result == ReadabilityResult.empty()


def test_collector_disabled_by_default():
    """Verify collector is disabled by default."""
    from homllm.intelligence.assertion_readability import ReadabilityCollector
    
    collector = ReadabilityCollector()
    assert collector.enabled is False


# =============================================================================
# READABILITY EVALUATION TESTS
# =============================================================================

def test_block_with_function_is_readable(mock_context, mock_diagnostics, mock_modification_plan, mock_block_diagnostic):
    """Verify block with functions is marked as readable."""
    from homllm.intelligence.assertion_readability import (
        ReadabilityCollector,
        ReadabilityReason,
    )
    
    blocks = (
        mock_block_diagnostic(block_id="block_1", function_count=1),
    )
    
    collector = ReadabilityCollector(enabled=True)
    
    result = collector.collect(
        mock_diagnostics(blocks=blocks),
        mock_modification_plan(),
        mock_context,
    )
    
    assert result.total_blocks == 1
    assert result.readable_count == 1
    assert result.suppressed_count == 0
    
    entry = result.entries[0]
    assert entry.readable is True
    assert ReadabilityReason.EXPLICIT_DEFINITION in entry.reasons


def test_block_with_class_is_readable(mock_context, mock_diagnostics, mock_modification_plan, mock_block_diagnostic):
    """Verify block with classes is marked as readable."""
    from homllm.intelligence.assertion_readability import (
        ReadabilityCollector,
        ReadabilityReason,
    )
    
    blocks = (
        mock_block_diagnostic(block_id="block_1", function_count=0, class_count=1),
    )
    
    collector = ReadabilityCollector(enabled=True)
    
    result = collector.collect(
        mock_diagnostics(blocks=blocks),
        mock_modification_plan(),
        mock_context,
    )
    
    assert result.readable_count == 1
    entry = result.entries[0]
    assert entry.readable is True
    assert ReadabilityReason.EXPLICIT_DEFINITION in entry.reasons


def test_block_with_control_flow_is_readable(mock_context, mock_diagnostics, mock_modification_plan, mock_block_diagnostic):
    """Verify block with control flow is marked as readable."""
    from homllm.intelligence.assertion_readability import (
        ReadabilityCollector,
        ReadabilityReason,
    )
    
    blocks = (
        mock_block_diagnostic(
            block_id="block_1",
            function_count=0,
            class_count=0,
            control_flow_lines=5,
        ),
    )
    
    collector = ReadabilityCollector(enabled=True)
    
    result = collector.collect(
        mock_diagnostics(blocks=blocks),
        mock_modification_plan(),
        mock_context,
    )
    
    entry = result.entries[0]
    assert entry.readable is True
    assert ReadabilityReason.CONTROL_FLOW in entry.reasons


def test_fragmented_block_not_readable(mock_context, mock_diagnostics, mock_modification_plan, mock_block_diagnostic):
    """Verify fragmented block with low signal is NOT readable."""
    from homllm.intelligence.assertion_readability import (
        ReadabilityCollector,
        ReadabilityReason,
    )
    
    blocks = (
        mock_block_diagnostic(
            block_id="block_1",
            function_count=0,
            class_count=0,
            method_count=0,
            control_flow_lines=0,
            code_lines=0,
            signature_lines=0,
            signal_ratio=0.1,
            noise_ratio=0.6,
        ),
    )
    
    collector = ReadabilityCollector(enabled=True)
    
    result = collector.collect(
        mock_diagnostics(blocks=blocks),
        mock_modification_plan(),
        mock_context,
    )
    
    assert result.suppressed_count == 1
    entry = result.entries[0]
    assert entry.readable is False
    assert ReadabilityReason.TOO_FRAGMENTED in entry.reasons


def test_protected_but_readable(mock_context, mock_diagnostics, mock_modification_plan, mock_block_diagnostic):
    """Verify protected block with functions is still marked readable."""
    from homllm.intelligence.assertion_readability import (
        ReadabilityCollector,
        ReadabilityReason,
    )
    from homllm.intelligence.controller import UnifiedAction
    
    blocks = (
        mock_block_diagnostic(block_id="block_1", function_count=1),
    )
    
    # Add protection action
    unified_actions = (
        UnifiedAction(
            level=1,
            action_type="PROTECT",
            target="block_1",
            priority=1,
            justification="Core definition",
            source_engine="level1",
            original_action=Mock(originating_rule="test_rule"),
        ),
    )
    
    collector = ReadabilityCollector(enabled=True)
    
    result = collector.collect(
        mock_diagnostics(blocks=blocks),
        mock_modification_plan(unified_actions=unified_actions),
        mock_context,
    )
    
    assert result.readable_count == 1
    assert result.protected_but_readable_count == 1
    
    entry = result.entries[0]
    assert entry.readable is True
    assert ReadabilityReason.PROTECTED_BUT_READABLE in entry.reasons
    assert "PROTECT" in entry.protecting_actions


# =============================================================================
# DETERMINISM TESTS
# =============================================================================

def test_evaluator_determinism(mock_context, mock_diagnostics, mock_modification_plan):
    """Verify same input produces same output."""
    from homllm.intelligence.assertion_readability import ReadabilityCollector
    
    collector = ReadabilityCollector(enabled=True)
    
    result1 = collector.collect(
        mock_diagnostics(),
        mock_modification_plan(),
        mock_context,
    )
    
    result2 = collector.collect(
        mock_diagnostics(),
        mock_modification_plan(),
        mock_context,
    )
    
    # Results should be identical
    assert result1.total_blocks == result2.total_blocks
    assert result1.readable_count == result2.readable_count
    assert result1.suppressed_count == result2.suppressed_count
    assert result1.protected_but_readable_count == result2.protected_but_readable_count


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================

def test_readability_result_to_dict(mock_context, mock_diagnostics, mock_modification_plan):
    """Verify ReadabilityResult can be serialized to dictionary."""
    from homllm.intelligence.assertion_readability import ReadabilityCollector
    import json
    
    collector = ReadabilityCollector(enabled=True)
    
    result = collector.collect(
        mock_diagnostics(),
        mock_modification_plan(),
        mock_context,
    )
    
    result_dict = result.to_dict()
    
    # Should be JSON serializable
    json_str = json.dumps(result_dict)
    assert json_str
    
    # Should contain expected fields
    assert "total_blocks" in result_dict
    assert "readable_count" in result_dict
    assert "suppressed_count" in result_dict
    assert "protected_but_readable_count" in result_dict
    assert "entries" in result_dict


def test_empty_readability_result_to_dict():
    """Verify empty ReadabilityResult serializes correctly."""
    from homllm.intelligence.assertion_readability import ReadabilityResult
    import json
    
    result = ReadabilityResult.empty()
    result_dict = result.to_dict()
    
    json_str = json.dumps(result_dict)
    assert json_str
    
    assert result_dict["total_blocks"] == 0
    assert result_dict["readable_count"] == 0


# =============================================================================
# IMMUTABILITY TESTS
# =============================================================================

def test_readability_result_frozen():
    """Verify ReadabilityResult is immutable."""
    from homllm.intelligence.assertion_readability import ReadabilityResult
    
    result = ReadabilityResult.empty()
    
    with pytest.raises(Exception):
        result.total_blocks = 10


def test_assertion_readability_frozen():
    """Verify AssertionReadability is immutable."""
    from homllm.intelligence.assertion_readability import AssertionReadability, ReadabilityReason
    
    ar = AssertionReadability(
        block_id="test",
        readable=True,
        reasons=(ReadabilityReason.EXPLICIT_DEFINITION,),
        protecting_actions=(),
    )
    
    with pytest.raises(Exception):
        ar.readable = False


# =============================================================================
# FACTORY FUNCTION TESTS
# =============================================================================

def test_factory_function_creates_collector():
    """Verify factory function creates valid collector."""
    from homllm.intelligence.assertion_readability import create_readability_collector
    
    collector = create_readability_collector(enabled=True)
    
    assert collector is not None
    assert collector.enabled is True


def test_factory_function_default_disabled():
    """Verify factory creates disabled collector by default."""
    from homllm.intelligence.assertion_readability import create_readability_collector
    
    collector = create_readability_collector()
    
    assert collector.enabled is False
