"""
Unit tests for Level-3 Cognitive Action Intelligence Engine.

Tests:
1. Determinism (same input → same plan)
2. Empty diagnostics handling
3. Action ordering stability
4. No mutation guarantees
5. Disable switch test
6. Graph node/edge limits
7. All actions have justifications
"""

import pytest


# =============================================================================
# IMPORT TESTS
# =============================================================================

def test_level3_imports_succeed():
    """Verify level3 module imports work correctly."""
    from homllm.intelligence.actions.level3 import (
        Level3ActionEngine,
        CognitiveActionPlan,
        CognitiveAction,
        CognitiveActionType,
        CognitiveGraph,
        ReasoningPath,
    )
    
    assert Level3ActionEngine is not None
    assert CognitiveActionPlan is not None
    assert CognitiveAction is not None
    assert CognitiveActionType is not None
    assert CognitiveGraph is not None
    assert ReasoningPath is not None


def test_no_forbidden_imports():
    """Verify level3 does not import from generation or models."""
    import ast
    from pathlib import Path
    
    level3_path = Path("src/homllm/intelligence/actions/level3")
    
    forbidden_patterns = [
        "homllm.generation",
        "homllm.models",
        "openai",
        "anthropic",
        "transformers",
    ]
    
    violations = []
    
    for py_file in level3_path.glob("*.py"):
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
# GRAPH TESTS
# =============================================================================

def test_cognitive_graph_node_limit():
    """Verify cognitive graph enforces max node limit (80)."""
    from homllm.intelligence.actions.level3 import CognitiveGraph, CognitiveNodeType
    
    graph = CognitiveGraph()
    
    # Add max nodes
    for i in range(graph.MAX_NODES):
        result = graph.add_node(f"node_{i}", CognitiveNodeType.REASONING_STEP, f"Node {i}")
        assert result is True
    
    # Next node should fail
    result = graph.add_node("overflow", CognitiveNodeType.REASONING_STEP, "Overflow")
    assert result is False
    assert graph.node_count == 80


def test_cognitive_graph_edge_limit():
    """Verify cognitive graph enforces max edges per node (4)."""
    from homllm.intelligence.actions.level3 import CognitiveGraph, CognitiveNodeType, CognitiveEdgeType
    
    graph = CognitiveGraph()
    graph.add_node("source", CognitiveNodeType.DECISION_POINT, "Source")
    
    # Add max edges
    for i in range(graph.MAX_EDGES_PER_NODE):
        graph.add_node(f"target_{i}", CognitiveNodeType.REASONING_STEP, f"Target {i}")
        result = graph.add_edge("source", f"target_{i}", CognitiveEdgeType.BRANCHES)
        assert result is True
    
    # Next edge from source should fail
    graph.add_node("overflow", CognitiveNodeType.REASONING_STEP, "Overflow")
    result = graph.add_edge("source", "overflow", CognitiveEdgeType.BRANCHES)
    assert result is False
    assert graph.edge_count == 4


def test_graph_depth_enforcement():
    """Verify max depth is enforced."""
    from homllm.intelligence.actions.level3 import CognitiveGraph, CognitiveNodeType
    
    graph = CognitiveGraph()
    
    # Try to add node with depth > MAX_DEPTH
    result = graph.add_node(
        "deep",
        CognitiveNodeType.REASONING_STEP,
        "Deep",
        depth=10,  # Exceeds MAX_DEPTH of 5
    )
    
    assert result is True
    node = graph.get_node("deep")
    assert node.depth == graph.MAX_DEPTH  # Should be clamped


def test_graph_branching_count():
    """Verify branching count calculation."""
    from homllm.intelligence.actions.level3 import CognitiveGraph, CognitiveNodeType, CognitiveEdgeType
    
    graph = CognitiveGraph()
    graph.add_node("decision", CognitiveNodeType.DECISION_POINT, "Decision")
    graph.add_node("branch1", CognitiveNodeType.REASONING_STEP, "Branch 1")
    graph.add_node("branch2", CognitiveNodeType.REASONING_STEP, "Branch 2")
    
    graph.add_edge("decision", "branch1", CognitiveEdgeType.BRANCHES)
    graph.add_edge("decision", "branch2", CognitiveEdgeType.BRANCHES)
    
    assert graph.count_branching("decision") == 2


# =============================================================================
# ACTION TESTS
# =============================================================================

def test_action_frozen():
    """Verify CognitiveAction is immutable."""
    from homllm.intelligence.actions.level3 import CognitiveAction, CognitiveActionType
    
    action = CognitiveAction(
        action_type=CognitiveActionType.ORDER,
        target="test_target",
        justification="Test reason",
    )
    
    with pytest.raises(Exception):
        action.target = "modified"


def test_action_priority():
    """Verify action priority is derived from type."""
    from homllm.intelligence.actions.level3 import CognitiveAction, CognitiveActionType
    
    order_action = CognitiveAction(
        action_type=CognitiveActionType.ORDER,
        target="a",
        justification="test",
    )
    separate_action = CognitiveAction(
        action_type=CognitiveActionType.SEPARATE,
        target="b",
        justification="test",
    )
    
    # ORDER (1) should have lower priority number than SEPARATE (6)
    assert order_action.priority < separate_action.priority


def test_plan_empty():
    """Verify empty plan creation."""
    from homllm.intelligence.actions.level3 import CognitiveActionPlan
    
    plan = CognitiveActionPlan.empty()
    
    assert len(plan.actions) == 0
    assert len(plan.reasoning_paths) == 0
    assert len(plan.invariants) == 0
    assert plan.total_paths == 0


# =============================================================================
# ENGINE TESTS
# =============================================================================

@pytest.fixture
def mock_diagnostics():
    """Create mock diagnostics for testing."""
    from homllm.intelligence.interfaces import (
        DiagnosticSnapshot,
        StructuralDiagnostics,
        SemanticDiagnostics,
        CognitiveDiagnostics,
    )
    
    def _create(l1_available=False, l3_available=False):
        return DiagnosticSnapshot(
            level1=StructuralDiagnostics(
                status="available" if l1_available else "unavailable",
                reason="" if l1_available else "test",
                blocks=(),
            ),
            level2=SemanticDiagnostics(
                status="unavailable",
                reason="test",
            ),
            level3=CognitiveDiagnostics(
                status="available" if l3_available else "unavailable",
                reason="" if l3_available else "test",
            ),
        )
    
    return _create


@pytest.fixture
def mock_context():
    """Create mock context for testing."""
    from homllm.context.interfaces import ContextArtifact
    
    return ContextArtifact(
        query_id="test_query",
        context_text="test content",
        blocks=(),
        token_budget=4000,
        used_tokens=10,
        provenance={},
        explain_trace=(),
    )


def test_disabled_engine_returns_empty(mock_diagnostics, mock_context):
    """Verify disabled engine returns empty plan."""
    from homllm.intelligence.actions.level3 import Level3ActionEngine
    
    engine = Level3ActionEngine(enabled=False)
    plan = engine.propose(mock_diagnostics(), mock_context)
    
    assert len(plan.actions) == 0
    assert plan.total_paths == 0


def test_no_diagnostics_returns_empty(mock_diagnostics, mock_context):
    """Verify missing L1 diagnostics returns empty plan."""
    from homllm.intelligence.actions.level3 import Level3ActionEngine
    
    engine = Level3ActionEngine(enabled=True)
    
    # No L1 available
    plan = engine.propose(mock_diagnostics(), mock_context)
    
    assert len(plan.actions) == 0


def test_engine_determinism(mock_diagnostics, mock_context):
    """Verify same input produces same output."""
    from homllm.intelligence.actions.level3 import Level3ActionEngine
    
    engine = Level3ActionEngine(enabled=True)
    diagnostics = mock_diagnostics(l1_available=True)
    
    plan1 = engine.propose(diagnostics, mock_context)
    plan2 = engine.propose(diagnostics, mock_context)
    
    assert len(plan1.actions) == len(plan2.actions)
    assert len(plan1.reasoning_paths) == len(plan2.reasoning_paths)
    assert len(plan1.invariants) == len(plan2.invariants)


# =============================================================================
# PATH TESTS
# =============================================================================

def test_reasoning_path_frozen():
    """Verify ReasoningPath is immutable."""
    from homllm.intelligence.actions.level3 import ReasoningPath, ReasoningStep
    
    path = ReasoningPath(
        path_id="test",
        steps=(ReasoningStep("s1", "step"),),
        invariants=("inv1",),
        entry_point="entry",
        exit_point="exit",
        complexity=1,
    )
    
    with pytest.raises(Exception):
        path.path_id = "modified"


def test_reasoning_step_frozen():
    """Verify ReasoningStep is immutable."""
    from homllm.intelligence.actions.level3 import ReasoningStep
    
    step = ReasoningStep(
        step_id="test",
        step_type="step",
        description="Test step",
    )
    
    with pytest.raises(Exception):
        step.step_id = "modified"


# =============================================================================
# INVARIANT TESTS
# =============================================================================

def test_invariant_protection_frozen():
    """Verify InvariantProtection is immutable."""
    from homllm.intelligence.actions.level3 import InvariantProtection
    
    inv = InvariantProtection(
        invariant_id="test",
        invariant_type="ordering",
        description="Test invariant",
        protected_blocks=("block1",),
        source="test",
    )
    
    with pytest.raises(Exception):
        inv.invariant_id = "modified"


# =============================================================================
# ACTION ORDERING TESTS
# =============================================================================

def test_action_ordering():
    """Verify actions are ordered by priority."""
    from homllm.intelligence.actions.level3 import (
        CognitiveAction,
        CognitiveActionType,
        COGNITIVE_ACTION_ORDER,
    )
    
    actions = [
        CognitiveAction(CognitiveActionType.SEPARATE, "z", justification="test"),
        CognitiveAction(CognitiveActionType.ORDER, "a", justification="test"),
        CognitiveAction(CognitiveActionType.ANCHOR, "m", justification="test"),
    ]
    
    type_priority = {t: i for i, t in enumerate(COGNITIVE_ACTION_ORDER)}
    sorted_actions = sorted(actions, key=lambda a: type_priority.get(a.action_type, 99))
    
    assert sorted_actions[0].action_type == CognitiveActionType.ORDER
    assert sorted_actions[-1].action_type == CognitiveActionType.SEPARATE


# =============================================================================
# INTEGRATION TEST
# =============================================================================

def test_full_pipeline_with_blocks(mock_context):
    """Test full pipeline with actual block data."""
    from homllm.intelligence.actions.level3 import Level3ActionEngine
    from homllm.intelligence.interfaces import (
        DiagnosticSnapshot,
        StructuralDiagnostics,
        SemanticDiagnostics,
        CognitiveDiagnostics,
    )
    from homllm.intelligence.diagnostics.inspect_context import (
        IntraBlockDiagnostic,
        TokenBreakdown,
        IdentifierDensity,
        StructuralPayload,
        RedundancyHints,
    )
    
    # Create a simple block
    block = IntraBlockDiagnostic(
        block_id="test_block",
        file="test.py",
        symbol="test_function",
        tokens=100,
        token_breakdown=TokenBreakdown(),
        identifier_density=IdentifierDensity(),
        structural_payload=StructuralPayload(),
        redundancy_hints=RedundancyHints(),
        signal_ratio=0.7,
        noise_ratio=0.2,
    )
    
    diagnostics = DiagnosticSnapshot(
        level1=StructuralDiagnostics(
            status="available",
            reason="",
            blocks=(block,),
        ),
        level2=SemanticDiagnostics(status="unavailable", reason="test"),
        level3=CognitiveDiagnostics(status="unavailable", reason="test"),
    )
    
    engine = Level3ActionEngine(enabled=True)
    plan = engine.propose(diagnostics, mock_context)
    
    # Should produce a valid plan with at least the entry node
    assert plan is not None
    assert isinstance(plan.explanations, tuple)
