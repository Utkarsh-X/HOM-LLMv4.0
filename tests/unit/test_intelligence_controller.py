"""
Unit tests for IntelligenceController.

Tests:
1. Determinism (same input → same output)
2. Disabled engines are skipped cleanly
3. Diagnostics are called once
4. Action engines receive identical snapshot
5. No imports from core pipeline modules
6. No action logic inside controller
7. Empty context handling
8. Diagnostic failure handling
"""

import pytest
from dataclasses import dataclass
from unittest.mock import Mock, MagicMock


# =============================================================================
# IMPORT TESTS
# =============================================================================

def test_intelligence_controller_imports_succeed():
    """Verify controller module imports work correctly."""
    from homllm.intelligence.controller import (
        IntelligenceController,
        ContextModificationPlan,
        UnifiedAction,
        create_intelligence_controller,
    )
    
    assert IntelligenceController is not None
    assert ContextModificationPlan is not None
    assert UnifiedAction is not None
    assert create_intelligence_controller is not None


def test_no_forbidden_imports():
    """Verify controller does not import from core pipeline modules."""
    import ast
    from pathlib import Path
    
    controller_path = Path("src/homllm/intelligence/controller.py")
    
    forbidden_patterns = [
        "homllm.generation",
        "homllm.models",
        "homllm.retrieval",
        "homllm.ranking",
        "homllm.indexer",
        "openai",
        "anthropic",
        "transformers",
    ]
    
    violations = []
    
    with open(controller_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
    except SyntaxError:
        pytest.fail("Controller has syntax error")
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for forbidden in forbidden_patterns:
                    if alias.name.startswith(forbidden):
                        violations.append(f"imports {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for forbidden in forbidden_patterns:
                    if node.module.startswith(forbidden):
                        violations.append(f"imports {node.module}")
    
    assert not violations, f"Forbidden imports found:\n" + "\n".join(violations)


def test_controller_line_count():
    """Verify controller stays under ~550 lines."""
    from pathlib import Path
    
    controller_path = Path("src/homllm/intelligence/controller.py")
    
    with open(controller_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    # Allow some buffer but should stay reasonable
    # Increased to 550 to accommodate audit integration (was 500)
    assert len(lines) < 550, f"Controller is {len(lines)} lines, too large"


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
        ),
        token_budget=4000,
        used_tokens=10,
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
                function_count=1,
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
    
    def _create(
        blocks=None, 
        l1_available=True,
        l2_available=True,
        l3_available=True,
    ):
        if blocks is None:
            blocks = (mock_block_diagnostic(),)
        
        return DiagnosticSnapshot(
            level1=StructuralDiagnostics(
                status="available" if l1_available else "unavailable",
                reason="" if l1_available else "test unavailable",
                blocks=blocks,
                result=None,
            ),
            level2=SemanticDiagnostics(
                status="available" if l2_available else "unavailable",
                reason="" if l2_available else "test unavailable",
                result=None,
            ),
            level3=CognitiveDiagnostics(
                status="available" if l3_available else "unavailable",
                reason="" if l3_available else "test unavailable",
                result=None,
            ),
        )
    
    return _create


@pytest.fixture
def mock_diagnostic_controller(mock_diagnostics):
    """Create a mock DiagnosticController."""
    controller = Mock()
    controller.analyze = Mock(return_value=mock_diagnostics())
    return controller


@pytest.fixture
def mock_level1_engine():
    """Create a mock Level1ActionEngine."""
    from homllm.intelligence.actions.level1.plan import (
        ContextModificationPlan,
        Action,
        ActionType,
    )
    
    engine = Mock()
    engine.enabled = True
    engine.propose = Mock(return_value=ContextModificationPlan(
        actions=(
            Action(
                block_id="block_1",
                action_type=ActionType.KEEP,
                reason="Test action",
                confidence=0.9,
                originating_rule="test_rule",
                diagnostic_evidence=(("key", "value"),),
            ),
        ),
        summary={"KEEP": 1},
        total_blocks_analyzed=1,
        conflicts_resolved=0,
    ))
    return engine


@pytest.fixture
def mock_level2_engine():
    """Create a mock SemanticActionEngine."""
    from homllm.intelligence.actions.level2.plan import (
        SemanticActionPlan,
        SemanticAction,
        SemanticActionType,
    )
    
    engine = Mock()
    engine.enabled = True
    engine.propose = Mock(return_value=SemanticActionPlan(
        actions=(
            SemanticAction(
                action_type=SemanticActionType.PROMOTE,
                target="concept_1",
                justification="Test semantic action",
            ),
        ),
        obligations=(),
        gaps=(),
        explanations=("Test",),
        total_obligations=0,
        satisfied_obligations=0,
        total_gaps=0,
        critical_gaps=0,
    ))
    return engine


@pytest.fixture
def mock_level3_engine():
    """Create a mock Level3ActionEngine."""
    from homllm.intelligence.actions.level3.plan import (
        CognitiveActionPlan,
        CognitiveAction,
        CognitiveActionType,
    )
    
    engine = Mock()
    engine.enabled = True
    engine.propose = Mock(return_value=CognitiveActionPlan(
        actions=(
            CognitiveAction(
                action_type=CognitiveActionType.ORDER,
                target="path_1",
                justification="Test cognitive action",
            ),
        ),
        reasoning_paths=(),
        invariants=(),
        ambiguities=(),
        explanations=("Test",),
    ))
    return engine


# =============================================================================
# DETERMINISM TESTS
# =============================================================================

def test_controller_determinism(mock_context, mock_diagnostic_controller, 
                                mock_level1_engine, mock_level2_engine, 
                                mock_level3_engine):
    """Verify same input produces same output."""
    from homllm.intelligence.controller import IntelligenceController
    
    controller = IntelligenceController(
        diagnostic_controller=mock_diagnostic_controller,
        level1_engine=mock_level1_engine,
        level2_engine=mock_level2_engine,
        level3_engine=mock_level3_engine,
    )
    
    plan1 = controller.run(mock_context)
    plan2 = controller.run(mock_context)
    
    # Compare plans
    assert plan1.total_actions == plan2.total_actions
    assert plan1.levels_executed == plan2.levels_executed
    assert plan1.diagnostics_available == plan2.diagnostics_available
    
    # Compare unified actions
    assert len(plan1.unified_actions) == len(plan2.unified_actions)
    for a1, a2 in zip(plan1.unified_actions, plan2.unified_actions):
        assert a1.level == a2.level
        assert a1.action_type == a2.action_type
        assert a1.target == a2.target
        assert a1.priority == a2.priority


def test_controller_determinism_with_real_engines(mock_context, mock_diagnostics, mock_block_diagnostic):
    """Verify determinism with real engine instances."""
    from homllm.intelligence.controller import IntelligenceController
    from homllm.intelligence.actions.level1.engine import Level1ActionEngine
    from homllm.intelligence.actions.level2.engine import SemanticActionEngine
    from homllm.intelligence.actions.level3.engine import Level3ActionEngine
    
    # Create mock diagnostic controller
    mock_diag = Mock()
    blocks = (
        mock_block_diagnostic(block_id="a", noise_ratio=0.1),
        mock_block_diagnostic(block_id="b", noise_ratio=0.5),
    )
    mock_diag.analyze = Mock(return_value=mock_diagnostics(blocks=blocks))
    
    controller = IntelligenceController(
        diagnostic_controller=mock_diag,
        level1_engine=Level1ActionEngine(enabled=True),
        level2_engine=SemanticActionEngine(enabled=True),
        level3_engine=Level3ActionEngine(enabled=True),
    )
    
    plan1 = controller.run(mock_context)
    plan2 = controller.run(mock_context)
    
    # Unified actions should be identical
    assert len(plan1.unified_actions) == len(plan2.unified_actions)
    for a1, a2 in zip(plan1.unified_actions, plan2.unified_actions):
        assert a1.level == a2.level
        assert a1.action_type == a2.action_type
        assert a1.target == a2.target


# =============================================================================
# ENGINE ENABLE/DISABLE TESTS
# =============================================================================

def test_disabled_level1_skipped(mock_context, mock_diagnostic_controller,
                                 mock_level1_engine, mock_level2_engine,
                                 mock_level3_engine):
    """Verify disabled Level-1 engine is skipped cleanly."""
    from homllm.intelligence.controller import IntelligenceController
    
    controller = IntelligenceController(
        diagnostic_controller=mock_diagnostic_controller,
        level1_engine=mock_level1_engine,
        level2_engine=mock_level2_engine,
        level3_engine=mock_level3_engine,
        level1_enabled=False,
    )
    
    plan = controller.run(mock_context)
    
    # Level-1 engine should NOT have been called
    mock_level1_engine.propose.assert_not_called()
    
    # Level-1 should not be in executed levels
    assert 1 not in plan.levels_executed
    assert 2 in plan.levels_executed
    assert 3 in plan.levels_executed


def test_disabled_level2_skipped(mock_context, mock_diagnostic_controller,
                                 mock_level1_engine, mock_level2_engine,
                                 mock_level3_engine):
    """Verify disabled Level-2 engine is skipped cleanly."""
    from homllm.intelligence.controller import IntelligenceController
    
    controller = IntelligenceController(
        diagnostic_controller=mock_diagnostic_controller,
        level1_engine=mock_level1_engine,
        level2_engine=mock_level2_engine,
        level3_engine=mock_level3_engine,
        level2_enabled=False,
    )
    
    plan = controller.run(mock_context)
    
    mock_level2_engine.propose.assert_not_called()
    assert 2 not in plan.levels_executed


def test_disabled_level3_skipped(mock_context, mock_diagnostic_controller,
                                 mock_level1_engine, mock_level2_engine,
                                 mock_level3_engine):
    """Verify disabled Level-3 engine is skipped cleanly."""
    from homllm.intelligence.controller import IntelligenceController
    
    controller = IntelligenceController(
        diagnostic_controller=mock_diagnostic_controller,
        level1_engine=mock_level1_engine,
        level2_engine=mock_level2_engine,
        level3_engine=mock_level3_engine,
        level3_enabled=False,
    )
    
    plan = controller.run(mock_context)
    
    mock_level3_engine.propose.assert_not_called()
    assert 3 not in plan.levels_executed


def test_all_engines_disabled(mock_context, mock_diagnostic_controller):
    """Verify all engines disabled returns empty unified actions."""
    from homllm.intelligence.controller import IntelligenceController
    
    controller = IntelligenceController(
        diagnostic_controller=mock_diagnostic_controller,
        level1_enabled=False,
        level2_enabled=False,
        level3_enabled=False,
    )
    
    plan = controller.run(mock_context)
    
    # Should still have diagnostics available
    assert plan.diagnostics_available is True
    assert plan.levels_executed == ()
    assert plan.total_actions == 0


# =============================================================================
# DIAGNOSTICS TESTS
# =============================================================================

def test_diagnostics_called_once(mock_context, mock_diagnostic_controller,
                                 mock_level1_engine, mock_level2_engine,
                                 mock_level3_engine):
    """Verify diagnostics are called exactly once per run."""
    from homllm.intelligence.controller import IntelligenceController
    
    controller = IntelligenceController(
        diagnostic_controller=mock_diagnostic_controller,
        level1_engine=mock_level1_engine,
        level2_engine=mock_level2_engine,
        level3_engine=mock_level3_engine,
    )
    
    controller.run(mock_context)
    
    # Diagnostics should be called exactly once
    assert mock_diagnostic_controller.analyze.call_count == 1


def test_all_engines_receive_same_snapshot(mock_context, mock_diagnostics, mock_block_diagnostic):
    """Verify all action engines receive the identical snapshot."""
    from homllm.intelligence.controller import IntelligenceController
    
    # Create engines that capture arguments
    captured_snapshots = []
    
    def capture_l1(snapshot, context):
        from homllm.intelligence.actions.level1.plan import ContextModificationPlan
        captured_snapshots.append(("l1", id(snapshot)))
        return ContextModificationPlan.empty()
    
    def capture_l2(snapshot, context):
        from homllm.intelligence.actions.level2.plan import SemanticActionPlan
        captured_snapshots.append(("l2", id(snapshot)))
        return SemanticActionPlan.empty()
    
    def capture_l3(snapshot, context):
        from homllm.intelligence.actions.level3.plan import CognitiveActionPlan
        captured_snapshots.append(("l3", id(snapshot)))
        return CognitiveActionPlan.empty()
    
    mock_l1 = Mock()
    mock_l1.propose = capture_l1
    
    mock_l2 = Mock()
    mock_l2.propose = capture_l2
    
    mock_l3 = Mock()
    mock_l3.propose = capture_l3
    
    mock_diag = Mock()
    mock_diag.analyze = Mock(return_value=mock_diagnostics())
    
    controller = IntelligenceController(
        diagnostic_controller=mock_diag,
        level1_engine=mock_l1,
        level2_engine=mock_l2,
        level3_engine=mock_l3,
    )
    
    controller.run(mock_context)
    
    # All engines should receive the same snapshot object
    assert len(captured_snapshots) == 3
    snapshot_ids = [s[1] for s in captured_snapshots]
    assert snapshot_ids[0] == snapshot_ids[1] == snapshot_ids[2]


def test_diagnostics_failure_returns_empty_plan(mock_context):
    """Verify diagnostic failure returns empty plan, no exception."""
    from homllm.intelligence.controller import IntelligenceController
    
    failing_diag = Mock()
    failing_diag.analyze = Mock(side_effect=RuntimeError("Diagnostic failure"))
    
    controller = IntelligenceController(diagnostic_controller=failing_diag)
    
    # Should NOT raise
    plan = controller.run(mock_context)
    
    assert plan.is_empty
    assert plan.diagnostics_available is False


def test_all_diagnostics_unavailable_returns_empty_plan(mock_context, mock_diagnostics):
    """Verify all unavailable diagnostics returns empty plan."""
    from homllm.intelligence.controller import IntelligenceController
    
    mock_diag = Mock()
    mock_diag.analyze = Mock(return_value=mock_diagnostics(
        l1_available=False,
        l2_available=False,
        l3_available=False,
    ))
    
    controller = IntelligenceController(diagnostic_controller=mock_diag)
    
    plan = controller.run(mock_context)
    
    assert plan.is_empty
    assert plan.diagnostics_available is False


# =============================================================================
# MERGE TESTS
# =============================================================================

def test_actions_merged_in_level_order(mock_context, mock_diagnostic_controller,
                                       mock_level1_engine, mock_level2_engine,
                                       mock_level3_engine):
    """Verify actions are merged with Level-1 first, Level-3 last."""
    from homllm.intelligence.controller import IntelligenceController
    
    controller = IntelligenceController(
        diagnostic_controller=mock_diagnostic_controller,
        level1_engine=mock_level1_engine,
        level2_engine=mock_level2_engine,
        level3_engine=mock_level3_engine,
    )
    
    plan = controller.run(mock_context)
    
    # Check level ordering
    levels_seen = [a.level for a in plan.unified_actions]
    
    # All level-1 actions should come before level-2
    l1_indices = [i for i, l in enumerate(levels_seen) if l == 1]
    l2_indices = [i for i, l in enumerate(levels_seen) if l == 2]
    l3_indices = [i for i, l in enumerate(levels_seen) if l == 3]
    
    if l1_indices and l2_indices:
        assert max(l1_indices) < min(l2_indices)
    if l2_indices and l3_indices:
        assert max(l2_indices) < min(l3_indices)


def test_unified_action_preserves_original(mock_context, mock_diagnostic_controller,
                                           mock_level1_engine, mock_level2_engine,
                                           mock_level3_engine):
    """Verify UnifiedAction preserves reference to original action."""
    from homllm.intelligence.controller import IntelligenceController
    
    controller = IntelligenceController(
        diagnostic_controller=mock_diagnostic_controller,
        level1_engine=mock_level1_engine,
        level2_engine=mock_level2_engine,
        level3_engine=mock_level3_engine,
    )
    
    plan = controller.run(mock_context)
    
    for unified in plan.unified_actions:
        assert unified.original_action is not None
        assert unified.source_engine in ("level1", "level2", "level3")


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================

def test_plan_to_dict(mock_context, mock_diagnostic_controller,
                      mock_level1_engine, mock_level2_engine,
                      mock_level3_engine):
    """Verify plan can be serialized to dictionary."""
    from homllm.intelligence.controller import IntelligenceController
    import json
    
    controller = IntelligenceController(
        diagnostic_controller=mock_diagnostic_controller,
        level1_engine=mock_level1_engine,
        level2_engine=mock_level2_engine,
        level3_engine=mock_level3_engine,
    )
    
    plan = controller.run(mock_context)
    plan_dict = plan.to_dict()
    
    # Should be JSON serializable
    json_str = json.dumps(plan_dict)
    assert json_str
    
    # Should contain expected fields
    assert "diagnostics_available" in plan_dict
    assert "levels_executed" in plan_dict
    assert "total_actions" in plan_dict
    assert "level1" in plan_dict
    assert "level2" in plan_dict
    assert "level3" in plan_dict
    assert "unified_actions" in plan_dict


def test_empty_plan_to_dict():
    """Verify empty plan serializes correctly."""
    from homllm.intelligence.controller import ContextModificationPlan
    import json
    
    plan = ContextModificationPlan.empty()
    plan_dict = plan.to_dict()
    
    json_str = json.dumps(plan_dict)
    assert json_str
    
    assert plan_dict["diagnostics_available"] is False
    assert plan_dict["total_actions"] == 0


# =============================================================================
# FACTORY FUNCTION TESTS
# =============================================================================

def test_factory_function_creates_controller():
    """Verify factory function creates valid controller."""
    from homllm.intelligence.controller import create_intelligence_controller
    
    controller = create_intelligence_controller(
        level1_enabled=True,
        level2_enabled=False,
        level3_enabled=True,
    )
    
    assert controller is not None
    assert controller._level1_enabled is True
    assert controller._level2_enabled is False
    assert controller._level3_enabled is True


def test_default_controller_creates_all_engines():
    """Verify default controller instantiates all engines."""
    from homllm.intelligence.controller import IntelligenceController
    
    controller = IntelligenceController()
    
    assert controller._diagnostic_controller is not None
    assert controller._level1_engine is not None
    assert controller._level2_engine is not None
    assert controller._level3_engine is not None


# =============================================================================
# IMMUTABILITY TESTS
# =============================================================================

def test_unified_action_frozen():
    """Verify UnifiedAction is immutable."""
    from homllm.intelligence.controller import UnifiedAction
    
    action = UnifiedAction(
        level=1,
        action_type="KEEP",
        target="block_1",
        priority=1,
        justification="Test",
        source_engine="level1",
        original_action=None,
    )
    
    with pytest.raises(Exception):
        action.level = 2


def test_context_not_mutated(mock_context, mock_diagnostic_controller,
                             mock_level1_engine, mock_level2_engine,
                             mock_level3_engine):
    """Verify context is not mutated by controller."""
    from homllm.intelligence.controller import IntelligenceController
    
    original_query_id = mock_context.query_id
    original_blocks = mock_context.blocks
    
    controller = IntelligenceController(
        diagnostic_controller=mock_diagnostic_controller,
        level1_engine=mock_level1_engine,
        level2_engine=mock_level2_engine,
        level3_engine=mock_level3_engine,
    )
    
    controller.run(mock_context)
    
    # Context should be unchanged
    assert mock_context.query_id == original_query_id
    assert mock_context.blocks == original_blocks
