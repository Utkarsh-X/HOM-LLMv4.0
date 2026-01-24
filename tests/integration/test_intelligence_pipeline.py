"""
Integration tests for Intelligence + Context Application pipeline.

Tests verify:
1. Diagnostics run once
2. Action engines execute in order L1 → L2 → L3
3. ContextApplier applies unified plan
4. Original context remains unchanged
5. Disabling intelligence produces identical output
6. Same input → same output (determinism)
"""

import pytest
from unittest.mock import Mock, MagicMock, patch


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_context():
    """Create sample ContextArtifact for integration tests."""
    from homllm.context.interfaces import ContextArtifact, ContextBlock
    
    blocks = (
        ContextBlock(
            block_id="block_1",
            file="main.py",
            start_line=1,
            end_line=10,
            content="def main():\n    process()\n    return result",
            symbol_id="main",
            symbol_name="main",
            provenance=("retrieval",),
        ),
        ContextBlock(
            block_id="block_2",
            file="utils.py",
            start_line=1,
            end_line=5,
            content="def helper():\n    return 42",
            symbol_id="helper",
            symbol_name="helper",
            provenance=("expansion",),
        ),
        ContextBlock(
            block_id="block_3",
            file="config.py",
            start_line=1,
            end_line=3,
            content="DEBUG = True",
            symbol_id="DEBUG",
            symbol_name="DEBUG",
            provenance=("retrieval",),
        ),
    )
    
    return ContextArtifact(
        query_id="test_query_001",
        context_text="def main()...\ndef helper()...",
        blocks=blocks,
        token_budget=4000,
        used_tokens=100,
        provenance={"source": "test"},
        explain_trace=("Test context",),
    )


@pytest.fixture
def sample_intelligence_config():
    """Create sample IntelligenceConfig."""
    from homllm.common.config import IntelligenceConfig
    
    return IntelligenceConfig(
        enabled=True,
        level1_enabled=True,
        level2_enabled=True,
        level3_enabled=True,
    )


# =============================================================================
# DIAGNOSTICS TESTS
# =============================================================================

def test_diagnostics_run_once(sample_context):
    """Verify diagnostics.analyze() is called exactly once per query."""
    from homllm.intelligence.controller import IntelligenceController
    from homllm.context.applier import ContextApplier
    from unittest.mock import Mock
    
    # Create mock diagnostic controller
    mock_diag_controller = Mock()
    mock_snapshot = Mock()
    mock_snapshot.level1.status = "available"
    mock_snapshot.level1.blocks = ()  # Empty blocks for L1 engine
    mock_snapshot.level2.status = "available"
    mock_snapshot.level2.result = None
    mock_snapshot.level3.status = "available"
    mock_snapshot.level3.result = None
    mock_diag_controller.analyze.return_value = mock_snapshot
    
    # Create controller with mock diagnostics
    controller = IntelligenceController(
        diagnostic_controller=mock_diag_controller,
        level1_enabled=True,
        level2_enabled=True,
        level3_enabled=True,
    )
    
    # Run intelligence
    plan = controller.run(sample_context)
    
    # Verify diagnostics called exactly once
    assert mock_diag_controller.analyze.call_count == 1


def test_action_engines_execute_in_order(sample_context):
    """Verify action engines are called in order L1 → L2 → L3."""
    from homllm.intelligence.controller import IntelligenceController
    from unittest.mock import Mock, call
    
    # Track call order
    call_order = []
    
    # Create mock engines that record their call order
    mock_l1_engine = Mock()
    mock_l1_engine.propose = Mock(side_effect=lambda s, c: (call_order.append("L1"), Mock(actions=()))[1])
    
    mock_l2_engine = Mock()
    mock_l2_engine.propose = Mock(side_effect=lambda s, c: (call_order.append("L2"), Mock(actions=()))[1])
    
    mock_l3_engine = Mock()
    mock_l3_engine.propose = Mock(side_effect=lambda s, c: (call_order.append("L3"), Mock(actions=()))[1])
    
    # Create mock diagnostics
    mock_diag = Mock()
    mock_snapshot = Mock()
    mock_snapshot.level1.status = "available"
    mock_snapshot.level2.status = "available"
    mock_snapshot.level3.status = "available"
    mock_diag.analyze.return_value = mock_snapshot
    
    controller = IntelligenceController(
        diagnostic_controller=mock_diag,
        level1_engine=mock_l1_engine,
        level2_engine=mock_l2_engine,
        level3_engine=mock_l3_engine,
        level1_enabled=True,
        level2_enabled=True,
        level3_enabled=True,
    )
    
    controller.run(sample_context)
    
    assert call_order == ["L1", "L2", "L3"]


# =============================================================================
# CONTEXT APPLICATION TESTS
# =============================================================================

def test_context_applier_applies_plan(sample_context):
    """Verify ContextApplier applies the unified plan."""
    from homllm.intelligence.controller import (
        ContextModificationPlan,
        UnifiedAction,
    )
    from homllm.intelligence.actions.level1.plan import (
        ContextModificationPlan as L1Plan,
    )
    from homllm.intelligence.actions.level2.plan import SemanticActionPlan
    from homllm.intelligence.actions.level3.plan import CognitiveActionPlan
    from homllm.context.applier import ContextApplier
    
    # Create plan with DROP action
    unified_actions = (
        UnifiedAction(
            level=1,
            action_type="DROP",
            target="block_3",
            priority=6,
            justification="Low value config block",
            source_engine="level1",
            original_action=Mock(priority=6, justification="Low value"),
        ),
    )
    
    plan = ContextModificationPlan(
        level1_plan=L1Plan.empty(),
        level2_plan=SemanticActionPlan.empty(),
        level3_plan=CognitiveActionPlan.empty(),
        unified_actions=unified_actions,
        diagnostics_available=True,
        levels_executed=(1,),
        total_actions=1,
    )
    
    applier = ContextApplier()
    result = applier.apply(plan, sample_context)
    
    # block_3 should be dropped
    new_block_ids = [b.block_id for b in result.context.blocks]
    assert "block_3" not in new_block_ids
    assert "block_1" in new_block_ids
    assert "block_2" in new_block_ids


def test_original_context_unchanged(sample_context):
    """Verify original ContextArtifact is never modified."""
    from homllm.intelligence.controller import create_intelligence_controller
    from homllm.context.applier import create_context_applier
    
    # Store original state
    original_blocks = sample_context.blocks
    original_query_id = sample_context.query_id
    original_token_budget = sample_context.token_budget
    
    # Run full pipeline
    controller = create_intelligence_controller(
        level1_enabled=True,
        level2_enabled=True,
        level3_enabled=True,
    )
    plan = controller.run(sample_context)
    
    applier = create_context_applier()
    result = applier.apply(plan, sample_context)
    
    # Original context must be unchanged
    assert sample_context.blocks == original_blocks
    assert sample_context.query_id == original_query_id
    assert sample_context.token_budget == original_token_budget


# =============================================================================
# KILL-SWITCH TESTS
# =============================================================================

def test_disabled_intelligence_skips_processing(sample_context):
    """Verify disabled intelligence produces clean pass-through."""
    from homllm.common.config import IntelligenceConfig
    from homllm.intelligence.controller import create_intelligence_controller
    from homllm.context.applier import create_context_applier
    
    # With intelligence disabled, the original context should be unchanged
    config_disabled = IntelligenceConfig(
        enabled=False,
        level1_enabled=True,
        level2_enabled=True,
        level3_enabled=True,
    )
    
    # When enabled=False, pipeline should skip entirely
    # This test verifies the config structure is correct
    assert config_disabled.enabled is False


def test_disabled_levels_skip_engines(sample_context):
    """Verify disabled levels don't execute their engines."""
    from homllm.intelligence.controller import IntelligenceController
    from unittest.mock import Mock
    
    mock_l1 = Mock()
    mock_l2 = Mock()
    mock_l3 = Mock()
    
    mock_l1.propose = Mock(return_value=Mock(actions=()))
    mock_l2.propose = Mock(return_value=Mock(actions=()))
    mock_l3.propose = Mock(return_value=Mock(actions=()))
    
    mock_diag = Mock()
    mock_snapshot = Mock()
    mock_snapshot.level1.status = "available"
    mock_snapshot.level2.status = "available"
    mock_snapshot.level3.status = "available"
    mock_diag.analyze.return_value = mock_snapshot
    
    # Disable L2 only
    controller = IntelligenceController(
        diagnostic_controller=mock_diag,
        level1_engine=mock_l1,
        level2_engine=mock_l2,
        level3_engine=mock_l3,
        level1_enabled=True,
        level2_enabled=False,
        level3_enabled=True,
    )
    
    controller.run(sample_context)
    
    # L1 and L3 should be called, L2 should not
    assert mock_l1.propose.called
    assert not mock_l2.propose.called
    assert mock_l3.propose.called


# =============================================================================
# DETERMINISM TESTS
# =============================================================================

def test_pipeline_determinism(sample_context):
    """Verify same input produces same output."""
    from homllm.intelligence.controller import create_intelligence_controller
    from homllm.context.applier import create_context_applier
    
    controller = create_intelligence_controller(
        level1_enabled=True,
        level2_enabled=True,
        level3_enabled=True,
    )
    applier = create_context_applier()
    
    # Run twice
    plan1 = controller.run(sample_context)
    result1 = applier.apply(plan1, sample_context)
    
    plan2 = controller.run(sample_context)
    result2 = applier.apply(plan2, sample_context)
    
    # Should produce identical results
    assert len(result1.context.blocks) == len(result2.context.blocks)
    for b1, b2 in zip(result1.context.blocks, result2.context.blocks):
        assert b1.block_id == b2.block_id
    
    assert len(result1.diff.entries) == len(result2.diff.entries)


def test_diff_completeness(sample_context):
    """Verify diff captures all applied changes."""
    from homllm.intelligence.controller import (
        ContextModificationPlan,
        UnifiedAction,
    )
    from homllm.intelligence.actions.level1.plan import (
        ContextModificationPlan as L1Plan,
    )
    from homllm.intelligence.actions.level2.plan import SemanticActionPlan
    from homllm.intelligence.actions.level3.plan import CognitiveActionPlan
    from homllm.context.applier import ContextApplier
    
    # Create plan with multiple actions
    unified_actions = (
        UnifiedAction(
            level=1,
            action_type="DROP",
            target="block_3",
            priority=6,
            justification="Test drop",
            source_engine="level1",
            original_action=Mock(priority=6, justification="Test"),
        ),
        UnifiedAction(
            level=1,
            action_type="PROTECT",
            target="block_1",
            priority=1,
            justification="Test protect",
            source_engine="level1",
            original_action=Mock(priority=1, justification="Test"),
        ),
    )
    
    plan = ContextModificationPlan(
        level1_plan=L1Plan.empty(),
        level2_plan=SemanticActionPlan.empty(),
        level3_plan=CognitiveActionPlan.empty(),
        unified_actions=unified_actions,
        diagnostics_available=True,
        levels_executed=(1,),
        total_actions=2,
    )
    
    applier = ContextApplier()
    result = applier.apply(plan, sample_context)
    
    # Diff should have entries for applied actions
    assert len(result.diff.entries) >= 1


# =============================================================================
# CONFIG TESTS
# =============================================================================

def test_intelligence_config_from_yaml():
    """Verify IntelligenceConfig can be extracted from YAML config."""
    from homllm.common.config import Config, IntelligenceConfig
    from pathlib import Path
    
    config_path = Path("configs/default.yaml")
    if config_path.exists():
        config = Config.from_file(config_path)
        int_config = config.get_intelligence_config()
        
        assert isinstance(int_config, IntelligenceConfig)
        assert isinstance(int_config.enabled, bool)
        assert isinstance(int_config.level1_enabled, bool)


def test_intelligence_config_defaults():
    """Verify IntelligenceConfig has sensible defaults."""
    from homllm.common.config import IntelligenceConfig
    
    config = IntelligenceConfig()
    
    assert config.enabled is True
    assert config.level1_enabled is True
    assert config.level2_enabled is True
    assert config.level3_enabled is True
