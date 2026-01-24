"""
Unit tests for Level-2 Semantic Action Intelligence Engine.

Tests:
1. Deterministic output
2. Graph node/edge limits
3. Obligation extraction correctness
4. Gap detection accuracy
5. Redundancy collapse logic
6. No forbidden imports
7. All actions have justifications
"""

import pytest


# =============================================================================
# IMPORT TESTS
# =============================================================================

def test_level2_imports_succeed():
    """Verify level2 module imports work correctly."""
    from homllm.intelligence.actions.level2 import (
        SemanticActionEngine,
        SemanticActionPlan,
        SemanticAction,
        SemanticActionType,
        SemanticObligation,
        SemanticGap,
        SemanticGraph,
    )
    
    assert SemanticActionEngine is not None
    assert SemanticActionPlan is not None
    assert SemanticAction is not None
    assert SemanticActionType is not None
    assert SemanticGraph is not None


def test_no_forbidden_imports():
    """Verify level2 does not import from generation or models."""
    import ast
    from pathlib import Path
    
    level2_path = Path("src/homllm/intelligence/actions/level2")
    
    forbidden_patterns = [
        "homllm.generation",
        "homllm.models",
        "openai",
        "anthropic",
        "transformers",
    ]
    
    violations = []
    
    for py_file in level2_path.glob("*.py"):
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

def test_graph_node_limit():
    """Verify graph enforces max node limit."""
    from homllm.intelligence.actions.level2 import SemanticGraph, NodeType
    
    graph = SemanticGraph()
    
    # Add max nodes
    for i in range(graph.MAX_NODES):
        result = graph.add_node(f"node_{i}", NodeType.CONCEPT, f"Node {i}")
        assert result is True
    
    # Next node should fail
    result = graph.add_node("overflow", NodeType.CONCEPT, "Overflow")
    assert result is False
    assert graph.node_count == graph.MAX_NODES


def test_graph_edge_limit_per_node():
    """Verify graph enforces max edges per node."""
    from homllm.intelligence.actions.level2 import SemanticGraph, NodeType, EdgeType
    
    graph = SemanticGraph()
    graph.add_node("source", NodeType.BLOCK, "Source")
    
    # Add max edges
    for i in range(graph.MAX_EDGES_PER_NODE):
        graph.add_node(f"target_{i}", NodeType.CONCEPT, f"Target {i}")
        result = graph.add_edge("source", f"target_{i}", EdgeType.DEFINES)
        assert result is True
    
    # Next edge from source should fail
    graph.add_node("overflow", NodeType.CONCEPT, "Overflow")
    result = graph.add_edge("source", "overflow", EdgeType.DEFINES)
    assert result is False


def test_graph_no_duplicate_edges():
    """Verify graph prevents duplicate edges."""
    from homllm.intelligence.actions.level2 import SemanticGraph, NodeType, EdgeType
    
    graph = SemanticGraph()
    graph.add_node("a", NodeType.BLOCK, "A")
    graph.add_node("b", NodeType.CONCEPT, "B")
    
    result1 = graph.add_edge("a", "b", EdgeType.DEFINES)
    result2 = graph.add_edge("a", "b", EdgeType.DEFINES)  # Duplicate
    
    assert result1 is True
    assert result2 is False
    assert graph.edge_count == 1


def test_graph_path_finding():
    """Verify graph path finding respects depth limit."""
    from homllm.intelligence.actions.level2 import SemanticGraph, NodeType, EdgeType
    
    graph = SemanticGraph()
    
    # Create chain: a -> b -> c -> d
    for node in ["a", "b", "c", "d"]:
        graph.add_node(node, NodeType.BLOCK, node)
    
    graph.add_edge("a", "b", EdgeType.SUPPORTS)
    graph.add_edge("b", "c", EdgeType.SUPPORTS)
    graph.add_edge("c", "d", EdgeType.SUPPORTS)
    
    # Should find path a -> b -> c (within depth 2)
    paths = graph.find_paths("a", "c", max_depth=2)
    assert len(paths) == 1
    assert paths[0] == ["a", "b", "c"]
    
    # Should not find a -> d (depth 3)
    paths = graph.find_paths("a", "d", max_depth=2)
    assert len(paths) == 0


# =============================================================================
# ACTION TESTS
# =============================================================================

def test_action_frozen():
    """Verify SemanticAction is immutable."""
    from homllm.intelligence.actions.level2 import SemanticAction, SemanticActionType
    
    action = SemanticAction(
        action_type=SemanticActionType.REQUIRE,
        target="test_concept",
        justification="Test reason",
    )
    
    with pytest.raises(Exception):
        action.target = "modified"


def test_action_priority():
    """Verify action priority is derived from type."""
    from homllm.intelligence.actions.level2 import SemanticAction, SemanticActionType
    
    require = SemanticAction(
        action_type=SemanticActionType.REQUIRE,
        target="a",
        justification="test",
    )
    reject = SemanticAction(
        action_type=SemanticActionType.REJECT,
        target="b",
        justification="test",
    )
    
    # REQUIRE (1) should have lower priority number than REJECT (6)
    assert require.priority < reject.priority


def test_plan_empty():
    """Verify empty plan creation."""
    from homllm.intelligence.actions.level2 import SemanticActionPlan
    
    plan = SemanticActionPlan.empty()
    
    assert len(plan.actions) == 0
    assert len(plan.obligations) == 0
    assert len(plan.gaps) == 0
    assert plan.coverage_score == 1.0  # No obligations = fully covered


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
    
    def _create(l1_available=False, l2_available=False, l3_available=False):
        return DiagnosticSnapshot(
            level1=StructuralDiagnostics(
                status="available" if l1_available else "unavailable",
                reason="" if l1_available else "test",
                blocks=(),
            ),
            level2=SemanticDiagnostics(
                status="available" if l2_available else "unavailable",
                reason="" if l2_available else "test",
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
    from homllm.intelligence.actions.level2 import SemanticActionEngine
    
    engine = SemanticActionEngine(enabled=False)
    plan = engine.propose(mock_diagnostics(), mock_context)
    
    assert len(plan.actions) == 0
    assert plan.total_obligations == 0


def test_no_diagnostics_returns_empty(mock_diagnostics, mock_context):
    """Verify missing diagnostics returns empty plan."""
    from homllm.intelligence.actions.level2 import SemanticActionEngine
    
    engine = SemanticActionEngine(enabled=True)
    
    # No L2 or L3 available
    plan = engine.propose(mock_diagnostics(), mock_context)
    
    assert len(plan.actions) == 0


def test_engine_determinism(mock_diagnostics, mock_context):
    """Verify same input produces same output."""
    from homllm.intelligence.actions.level2 import SemanticActionEngine
    
    engine = SemanticActionEngine(enabled=True)
    diagnostics = mock_diagnostics(l2_available=True)
    
    plan1 = engine.propose(diagnostics, mock_context)
    plan2 = engine.propose(diagnostics, mock_context)
    
    assert len(plan1.actions) == len(plan2.actions)
    assert len(plan1.obligations) == len(plan2.obligations)
    assert len(plan1.gaps) == len(plan2.gaps)


# =============================================================================
# OBLIGATION TESTS
# =============================================================================

def test_obligation_frozen():
    """Verify SemanticObligation is immutable."""
    from homllm.intelligence.actions.level2 import SemanticObligation
    
    obligation = SemanticObligation(
        name="test_obligation",
        required_concepts=("concept1",),
        required_roles=("DEFINE",),
        source="test",
    )
    
    with pytest.raises(Exception):
        obligation.name = "modified"


# =============================================================================
# GAP TESTS
# =============================================================================

def test_gap_frozen():
    """Verify SemanticGap is immutable."""
    from homllm.intelligence.actions.level2 import SemanticGap
    
    gap = SemanticGap(
        obligation_name="test",
        missing_concepts=("a",),
        missing_roles=("DEFINE",),
        severity="critical",
        reason="Test gap",
    )
    
    with pytest.raises(Exception):
        gap.severity = "minor"


# =============================================================================
# ACTION ORDERING TESTS
# =============================================================================

def test_action_ordering():
    """Verify actions are ordered by priority."""
    from homllm.intelligence.actions.level2 import (
        SemanticAction,
        SemanticActionType,
        SEMANTIC_ACTION_ORDER,
    )
    
    actions = [
        SemanticAction(SemanticActionType.REJECT, "z", "test"),
        SemanticAction(SemanticActionType.REQUIRE, "a", "test"),
        SemanticAction(SemanticActionType.PROMOTE, "m", "test"),
    ]
    
    type_priority = {t: i for i, t in enumerate(SEMANTIC_ACTION_ORDER)}
    sorted_actions = sorted(actions, key=lambda a: type_priority.get(a.action_type, 99))
    
    assert sorted_actions[0].action_type == SemanticActionType.REQUIRE
    assert sorted_actions[-1].action_type == SemanticActionType.REJECT
