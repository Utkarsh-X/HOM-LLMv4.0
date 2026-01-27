"""
Unit tests for AuditCollector.

Tests:
1. Determinism (same input → same output)
2. Disabled collector returns empty result
3. Suppression detection (PROTECT action → assertion marked suppressed)
4. Level attribution (actions correctly attributed to L1/L2/L3)
5. No behavior change when audit disabled
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
        noise_ratio: float = 0.2,
        signal_ratio: float = 0.7,
        function_count: int = 1,
    ) -> IntraBlockDiagnostic:
        return IntraBlockDiagnostic(
            block_id=block_id,
            file="test.py",
            symbol="test_function",
            tokens=100,
            token_breakdown=TokenBreakdown(
                logging_pct=5.0,
                docstrings_pct=10.0,
            ),
            identifier_density=IdentifierDensity(),
            structural_payload=StructuralPayload(
                function_count=function_count,
                class_count=0,
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
                mock_block_diagnostic(block_id="block_1"),
                mock_block_diagnostic(block_id="block_2"),
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
        Action as L1Action,
        ActionType,
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

def test_audit_module_imports_succeed():
    """Verify audit module imports work correctly."""
    from homllm.intelligence.audit import (
        AuditCollector,
        AuditResult,
        AssertionCandidate,
        SuppressionReason,
        create_audit_collector,
    )
    
    assert AuditCollector is not None
    assert AuditResult is not None
    assert AssertionCandidate is not None
    assert SuppressionReason is not None
    assert create_audit_collector is not None


# =============================================================================
# DISABLED COLLECTOR TESTS
# =============================================================================

def test_disabled_collector_returns_empty_result(mock_context, mock_diagnostics, mock_modification_plan):
    """Verify disabled collector returns empty AuditResult."""
    from homllm.intelligence.audit import AuditCollector, AuditResult
    
    collector = AuditCollector(enabled=False)
    
    result = collector.collect(
        mock_diagnostics(),
        mock_modification_plan(),
        mock_context,
    )
    
    assert result.total_assertions_considered == 0
    assert result.assertions_suppressed == 0
    assert result.assertions_unblocked == 0
    assert result == AuditResult.empty()


def test_disabled_by_default():
    """Verify collector is disabled by default."""
    from homllm.intelligence.audit import AuditCollector
    
    collector = AuditCollector()
    assert collector.enabled is False


# =============================================================================
# ENABLED COLLECTOR TESTS
# =============================================================================

def test_enabled_collector_extracts_assertions(mock_context, mock_diagnostics, mock_modification_plan):
    """Verify enabled collector extracts assertion candidates from blocks."""
    from homllm.intelligence.audit import AuditCollector
    
    collector = AuditCollector(enabled=True)
    
    result = collector.collect(
        mock_diagnostics(),
        mock_modification_plan(),
        mock_context,
    )
    
    # Should have one assertion per block in diagnostics
    assert result.total_assertions_considered == 2
    assert len(result.entries) == 2


def test_collector_detects_protective_action(mock_context, mock_diagnostics, mock_modification_plan):
    """Verify collector detects PROTECT actions as suppressions."""
    from homllm.intelligence.audit import AuditCollector
    from homllm.intelligence.controller import UnifiedAction
    from homllm.intelligence.actions.level1.plan import Action, ActionType
    
    # Create mock action with originating_rule attribute
    mock_action = Action(
        block_id="block_1",
        action_type=ActionType.PROTECT,
        reason="Core definition",
        confidence=0.9,
        originating_rule="role_define_protect",
        diagnostic_evidence=(),
    )
    
    unified_actions = (
        UnifiedAction(
            level=1,
            action_type="PROTECT",
            target="block_1",
            priority=1,
            justification="Core definition",
            source_engine="level1",
            original_action=mock_action,
        ),
    )
    
    collector = AuditCollector(enabled=True)
    
    result = collector.collect(
        mock_diagnostics(),
        mock_modification_plan(unified_actions=unified_actions),
        mock_context,
    )
    
    # One assertion should be suppressed (block_1)
    assert result.assertions_suppressed >= 1
    
    # Find the entry for block_1
    block_1_entry = next(
        (e for e in result.entries if "block_1" in e.assertion.supporting_blocks),
        None
    )
    assert block_1_entry is not None
    assert block_1_entry.is_suppressed is True
    assert len(block_1_entry.suppression_reasons) >= 1
    assert block_1_entry.suppression_reasons[0].action_type == "PROTECT"
    assert block_1_entry.suppression_reasons[0].level == 1


def test_collector_level_attribution(mock_context, mock_diagnostics, mock_modification_plan):
    """Verify collector correctly attributes actions to levels."""
    from homllm.intelligence.audit import AuditCollector
    from homllm.intelligence.controller import UnifiedAction
    
    # Create actions at different levels
    unified_actions = (
        UnifiedAction(
            level=1,
            action_type="PROTECT",
            target="block_1",
            priority=1,
            justification="L1 action",
            source_engine="level1",
            original_action=Mock(originating_rule="test_rule_l1"),
        ),
        UnifiedAction(
            level=3,
            action_type="ANCHOR",
            target="block_2",
            priority=2,
            justification="L3 action",
            source_engine="level3",
            original_action=Mock(originating_rule="test_rule_l3"),
        ),
    )
    
    collector = AuditCollector(enabled=True)
    
    result = collector.collect(
        mock_diagnostics(),
        mock_modification_plan(unified_actions=unified_actions),
        mock_context,
    )
    
    # Check level attribution in breakdown
    breakdown_dict = dict(result.suppression_breakdown_by_level)
    
    # Both blocks should be suppressed
    assert result.assertions_suppressed == 2
    
    # Check that levels are correctly attributed
    block_1_entry = next(
        (e for e in result.entries if "block_1" in e.assertion.supporting_blocks),
        None
    )
    assert block_1_entry is not None
    assert block_1_entry.suppression_reasons[0].level == 1
    
    block_2_entry = next(
        (e for e in result.entries if "block_2" in e.assertion.supporting_blocks),
        None
    )
    assert block_2_entry is not None
    assert block_2_entry.suppression_reasons[0].level == 3


# =============================================================================
# DETERMINISM TESTS
# =============================================================================

def test_collector_determinism(mock_context, mock_diagnostics, mock_modification_plan):
    """Verify same input produces same output."""
    from homllm.intelligence.audit import AuditCollector
    from homllm.intelligence.controller import UnifiedAction
    
    unified_actions = (
        UnifiedAction(
            level=1,
            action_type="PROTECT",
            target="block_1",
            priority=1,
            justification="Test",
            source_engine="level1",
            original_action=Mock(originating_rule="test_rule"),
        ),
    )
    
    collector = AuditCollector(enabled=True)
    
    result1 = collector.collect(
        mock_diagnostics(),
        mock_modification_plan(unified_actions=unified_actions),
        mock_context,
    )
    
    result2 = collector.collect(
        mock_diagnostics(),
        mock_modification_plan(unified_actions=unified_actions),
        mock_context,
    )
    
    # Results should be identical
    assert result1.total_assertions_considered == result2.total_assertions_considered
    assert result1.assertions_suppressed == result2.assertions_suppressed
    assert result1.assertions_unblocked == result2.assertions_unblocked
    assert result1.suppression_breakdown_by_level == result2.suppression_breakdown_by_level


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================

def test_audit_result_to_dict(mock_context, mock_diagnostics, mock_modification_plan):
    """Verify AuditResult can be serialized to dictionary."""
    from homllm.intelligence.audit import AuditCollector
    import json
    
    collector = AuditCollector(enabled=True)
    
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
    assert "total_assertions_considered" in result_dict
    assert "assertions_suppressed" in result_dict
    assert "assertions_unblocked" in result_dict
    assert "suppression_breakdown_by_level" in result_dict
    assert "entries" in result_dict


def test_empty_audit_result_to_dict():
    """Verify empty AuditResult serializes correctly."""
    from homllm.intelligence.audit import AuditResult
    import json
    
    result = AuditResult.empty()
    result_dict = result.to_dict()
    
    json_str = json.dumps(result_dict)
    assert json_str
    
    assert result_dict["total_assertions_considered"] == 0
    assert result_dict["assertions_suppressed"] == 0


# =============================================================================
# IMMUTABILITY TESTS
# =============================================================================

def test_audit_result_frozen():
    """Verify AuditResult is immutable."""
    from homllm.intelligence.audit import AuditResult
    
    result = AuditResult.empty()
    
    with pytest.raises(Exception):
        result.total_assertions_considered = 10


def test_assertion_candidate_frozen():
    """Verify AssertionCandidate is immutable."""
    from homllm.intelligence.audit import AssertionCandidate
    
    candidate = AssertionCandidate(
        assertion_id="test",
        textual_form="Test claim",
        supporting_blocks=("block_1",),
        confidence_signal=0.8,
    )
    
    with pytest.raises(Exception):
        candidate.textual_form = "Modified"


# =============================================================================
# FACTORY FUNCTION TESTS
# =============================================================================

def test_factory_function_creates_collector():
    """Verify factory function creates valid collector."""
    from homllm.intelligence.audit import create_audit_collector
    
    collector = create_audit_collector(enabled=True)
    
    assert collector is not None
    assert collector.enabled is True


def test_factory_function_default_disabled():
    """Verify factory creates disabled collector by default."""
    from homllm.intelligence.audit import create_audit_collector
    
    collector = create_audit_collector()
    
    assert collector.enabled is False
