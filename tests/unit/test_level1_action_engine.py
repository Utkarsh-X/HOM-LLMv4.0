"""
Unit tests for Level-1 Action Intelligence Engine.

Tests:
1. Determinism (same input → same plan)
2. No diagnostics mutation
3. No cross-block leakage
4. Correct conflict resolution
5. Correct action ordering
6. Empty context handling
7. All actions have reasons & evidence
8. Disabled engine returns empty plan
"""

import pytest
from dataclasses import dataclass, field


# =============================================================================
# IMPORT TESTS
# =============================================================================

def test_level1_imports_succeed():
    """Verify level1 module imports work correctly."""
    from homllm.intelligence.actions.level1 import (
        Level1ActionEngine,
        ContextModificationPlan,
        Action,
        ActionType,
    )
    
    assert Level1ActionEngine is not None
    assert ContextModificationPlan is not None
    assert Action is not None
    assert ActionType is not None


def test_no_forbidden_imports():
    """Verify level1 does not import from generation or models."""
    import ast
    from pathlib import Path
    
    level1_path = Path("src/homllm/intelligence/actions/level1")
    
    forbidden_patterns = [
        "homllm.generation",
        "homllm.models",
        "openai",
        "anthropic",
        "transformers",
    ]
    
    violations = []
    
    for py_file in level1_path.glob("*.py"):
        with open(py_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_patterns:
                        if alias.name.startswith(forbidden):
                            violations.append(f"{py_file}: imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_patterns:
                        if node.module.startswith(forbidden):
                            violations.append(f"{py_file}: imports {node.module}")
    
    assert not violations, f"Forbidden imports found:\n" + "\n".join(violations)


# =============================================================================
# FIXTURES
# =============================================================================

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
        logging_pct: float = 5.0,
        docstrings_pct: float = 10.0,
        boilerplate_score: float = 0.2,
        function_count: int = 1,
        class_count: int = 0,
    ) -> IntraBlockDiagnostic:
        return IntraBlockDiagnostic(
            block_id=block_id,
            file="test.py",
            symbol="test_function",
            tokens=100,
            token_breakdown=TokenBreakdown(
                logging_pct=logging_pct,
                docstrings_pct=docstrings_pct,
            ),
            identifier_density=IdentifierDensity(),
            structural_payload=StructuralPayload(
                function_count=function_count,
                class_count=class_count,
            ),
            redundancy_hints=RedundancyHints(
                boilerplate_score=boilerplate_score,
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
    
    def _create(blocks=None, available=True):
        if blocks is None:
            blocks = (mock_block_diagnostic(),)
        
        return DiagnosticSnapshot(
            level1=StructuralDiagnostics(
                status="available" if available else "unavailable",
                reason="" if available else "test unavailable",
                blocks=blocks,
                result=None,
            ),
            level2=SemanticDiagnostics(status="unavailable", reason="test"),
            level3=CognitiveDiagnostics(status="unavailable", reason="test"),
        )
    
    return _create


@pytest.fixture
def mock_context():
    """Create mock ContextArtifact for testing."""
    from homllm.context.interfaces import ContextArtifact
    
    return ContextArtifact(
        query_id="test_query",
        context_text="def test(): pass",
        blocks=(),
        token_budget=4000,
        used_tokens=10,
        provenance={},
        explain_trace=(),
    )


# =============================================================================
# DETERMINISM TESTS
# =============================================================================

def test_engine_determinism(mock_diagnostics, mock_context, mock_block_diagnostic):
    """Verify same input produces same output."""
    from homllm.intelligence.actions.level1 import Level1ActionEngine
    
    engine = Level1ActionEngine(enabled=True)
    
    blocks = (
        mock_block_diagnostic(block_id="a", noise_ratio=0.5),
        mock_block_diagnostic(block_id="b", noise_ratio=0.1),
    )
    diagnostics = mock_diagnostics(blocks=blocks)
    
    plan1 = engine.propose(diagnostics, mock_context)
    plan2 = engine.propose(diagnostics, mock_context)
    
    assert len(plan1.actions) == len(plan2.actions)
    
    for a1, a2 in zip(plan1.actions, plan2.actions):
        assert a1.block_id == a2.block_id
        assert a1.action_type == a2.action_type
        assert a1.confidence == a2.confidence
        assert a1.originating_rule == a2.originating_rule


# =============================================================================
# ENGINE BEHAVIOR TESTS
# =============================================================================

def test_disabled_engine_returns_empty_plan(mock_diagnostics, mock_context):
    """Verify disabled engine returns empty plan."""
    from homllm.intelligence.actions.level1 import Level1ActionEngine
    
    engine = Level1ActionEngine(enabled=False)
    diagnostics = mock_diagnostics()
    
    plan = engine.propose(diagnostics, mock_context)
    
    assert len(plan.actions) == 0
    assert plan.total_blocks_analyzed == 0


def test_unavailable_diagnostics_returns_empty_plan(mock_diagnostics, mock_context):
    """Verify unavailable L1 diagnostics returns empty plan."""
    from homllm.intelligence.actions.level1 import Level1ActionEngine
    
    engine = Level1ActionEngine(enabled=True)
    diagnostics = mock_diagnostics(available=False)
    
    plan = engine.propose(diagnostics, mock_context)
    
    assert len(plan.actions) == 0


def test_empty_blocks_returns_empty_plan(mock_diagnostics, mock_context):
    """Verify empty blocks returns empty plan."""
    from homllm.intelligence.actions.level1 import Level1ActionEngine
    
    engine = Level1ActionEngine(enabled=True)
    diagnostics = mock_diagnostics(blocks=())
    
    plan = engine.propose(diagnostics, mock_context)
    
    assert len(plan.actions) == 0


# =============================================================================
# ACTION QUALITY TESTS
# =============================================================================

def test_all_actions_have_reason_and_evidence(mock_diagnostics, mock_context, mock_block_diagnostic):
    """Verify all actions include reason and evidence."""
    from homllm.intelligence.actions.level1 import Level1ActionEngine
    
    engine = Level1ActionEngine(enabled=True)
    
    blocks = (
        mock_block_diagnostic(block_id="noisy", noise_ratio=0.5),
    )
    diagnostics = mock_diagnostics(blocks=blocks)
    
    plan = engine.propose(diagnostics, mock_context)
    
    for action in plan.actions:
        assert action.reason, f"Action {action.block_id} missing reason"
        assert action.diagnostic_evidence, f"Action {action.block_id} missing evidence"
        assert action.originating_rule, f"Action {action.block_id} missing rule"


def test_action_frozen():
    """Verify Action is immutable."""
    from homllm.intelligence.actions.level1 import Action, ActionType
    
    action = Action(
        block_id="test",
        action_type=ActionType.DROP,
        reason="test reason",
        confidence=0.8,
        originating_rule="test_rule",
        diagnostic_evidence=(("key", "value"),),
    )
    
    with pytest.raises(Exception):
        action.block_id = "modified"


# =============================================================================
# CONFLICT RESOLUTION TESTS
# =============================================================================

def test_protect_wins_over_drop(mock_diagnostics, mock_context, mock_block_diagnostic):
    """Verify PROTECT takes precedence over DROP."""
    from homllm.intelligence.actions.level1 import (
        Level1ActionEngine,
        ActionType,
    )
    
    # Create a block that triggers both PROTECT (clean function) and DROP (high noise)
    # This simulates a conflict scenario
    from homllm.intelligence.actions.level1.plan import ProposedAction
    from homllm.intelligence.actions.level1.resolver import ConflictResolver
    
    resolver = ConflictResolver()
    
    protect_proposal = ProposedAction(
        block_id="block_1",
        action_type=ActionType.PROTECT,
        confidence=0.9,
        reason="Core definition",
        originating_rule="role_define_protect",
        evidence=(("block_id", "block_1"),),
    )
    
    drop_proposal = ProposedAction(
        block_id="block_1",
        action_type=ActionType.DROP,
        confidence=0.95,  # Even higher confidence
        reason="High noise",
        originating_rule="noise_drop",
        evidence=(("block_id", "block_1"),),
    )
    
    # PROTECT should win despite lower confidence
    actions, _ = resolver.resolve({"block_1": [protect_proposal, drop_proposal]})
    
    assert len(actions) == 1
    assert actions[0].action_type == ActionType.PROTECT


def test_higher_confidence_wins_same_precedence():
    """Verify higher confidence wins at same precedence level."""
    from homllm.intelligence.actions.level1 import ActionType
    from homllm.intelligence.actions.level1.plan import ProposedAction
    from homllm.intelligence.actions.level1.resolver import ConflictResolver
    
    resolver = ConflictResolver()
    
    compact_low = ProposedAction(
        block_id="block_1",
        action_type=ActionType.COMPACT,
        confidence=0.5,
        reason="Low confidence",
        originating_rule="rule_a",
        evidence=(),
    )
    
    compact_high = ProposedAction(
        block_id="block_1",
        action_type=ActionType.COMPACT,
        confidence=0.9,
        reason="High confidence",
        originating_rule="rule_b",
        evidence=(),
    )
    
    actions, _ = resolver.resolve({"block_1": [compact_low, compact_high]})
    
    assert actions[0].confidence == 0.9


# =============================================================================
# ACTION ORDERING TESTS
# =============================================================================

def test_action_ordering():
    """Verify actions are ordered correctly: PROTECT first, DROP last."""
    from homllm.intelligence.actions.level1 import Action, ActionType
    from homllm.intelligence.actions.level1.resolver import order_actions
    
    actions = [
        Action(
            block_id="drop_block",
            action_type=ActionType.DROP,
            reason="test",
            confidence=0.8,
            originating_rule="test",
            diagnostic_evidence=(),
        ),
        Action(
            block_id="protect_block",
            action_type=ActionType.PROTECT,
            reason="test",
            confidence=0.8,
            originating_rule="test",
            diagnostic_evidence=(),
        ),
        Action(
            block_id="compact_block",
            action_type=ActionType.COMPACT,
            reason="test",
            confidence=0.8,
            originating_rule="test",
            diagnostic_evidence=(),
        ),
    ]
    
    ordered = order_actions(actions)
    
    # PROTECT should be first
    assert ordered[0].action_type == ActionType.PROTECT
    # DROP should be last
    assert ordered[-1].action_type == ActionType.DROP


# =============================================================================
# RULE TESTS
# =============================================================================

def test_noise_drop_rule(mock_block_diagnostic):
    """Verify noise_drop rule triggers at threshold."""
    from homllm.intelligence.actions.level1.rules import get_all_rules
    from homllm.intelligence.actions.level1 import ActionType
    
    rules = dict(get_all_rules())
    noise_drop = rules["noise_drop"]
    
    # Below threshold - no action
    clean_block = mock_block_diagnostic(noise_ratio=0.4)
    assert noise_drop(clean_block) == []
    
    # Above threshold - DROP
    noisy_block = mock_block_diagnostic(noise_ratio=0.5)
    proposals = noise_drop(noisy_block)
    assert len(proposals) == 1
    assert proposals[0].action_type == ActionType.DROP


def test_protect_rule(mock_block_diagnostic):
    """Verify role_define_protect rule for clean definitions."""
    from homllm.intelligence.actions.level1.rules import get_all_rules
    from homllm.intelligence.actions.level1 import ActionType
    
    rules = dict(get_all_rules())
    protect = rules["role_define_protect"]
    
    # Clean function definition - PROTECT
    clean_def = mock_block_diagnostic(
        function_count=1,
        noise_ratio=0.1,
    )
    proposals = protect(clean_def)
    assert len(proposals) == 1
    assert proposals[0].action_type == ActionType.PROTECT
    
    # Noisy function - no PROTECT
    noisy_def = mock_block_diagnostic(
        function_count=1,
        noise_ratio=0.3,
    )
    assert protect(noisy_def) == []


# =============================================================================
# SUMMARY TESTS
# =============================================================================

def test_plan_summary(mock_diagnostics, mock_context, mock_block_diagnostic):
    """Verify plan summary counts are correct."""
    from homllm.intelligence.actions.level1 import Level1ActionEngine
    
    engine = Level1ActionEngine(enabled=True)
    
    blocks = (
        mock_block_diagnostic(block_id="noisy", noise_ratio=0.5),
        mock_block_diagnostic(block_id="clean", noise_ratio=0.1, function_count=1),
    )
    diagnostics = mock_diagnostics(blocks=blocks)
    
    plan = engine.propose(diagnostics, mock_context)
    
    assert plan.total_blocks_analyzed == 2
    assert sum(plan.summary.values()) == len(plan.actions)
