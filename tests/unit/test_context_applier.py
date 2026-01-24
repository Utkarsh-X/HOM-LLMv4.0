"""
Unit tests for Context Application Layer.

Tests:
1. No context mutation
2. Determinism (same input → same output)
3. Drop action removes block
4. Protect action prevents removal
5. Conflict resolution (L3 > L2 > L1)
6. Token budget enforcement
7. Diff completeness
8. Empty plan returns unchanged context
9. No forbidden imports
"""

import pytest
from unittest.mock import Mock, MagicMock


# =============================================================================
# IMPORT TESTS
# =============================================================================

def test_context_applier_imports_succeed():
    """Verify applier module imports work correctly."""
    from homllm.context.applier import (
        ContextApplier,
        ApplierConfig,
        ApplierResult,
        create_context_applier,
    )
    
    assert ContextApplier is not None
    assert ApplierConfig is not None
    assert ApplierResult is not None
    assert create_context_applier is not None


def test_diff_imports_succeed():
    """Verify diff module imports work correctly."""
    from homllm.context.diff import (
        ContextDiff,
        DiffEntry,
        ConflictRecord,
        DiffBuilder,
    )
    
    assert ContextDiff is not None
    assert DiffEntry is not None
    assert ConflictRecord is not None
    assert DiffBuilder is not None


def test_no_forbidden_imports_in_applier():
    """Verify applier does not import from forbidden modules."""
    import ast
    from pathlib import Path
    
    applier_path = Path("src/homllm/context/applier.py")
    
    forbidden_patterns = [
        "homllm.intelligence.diagnostics",
        "homllm.intelligence.actions",
        "homllm.generation",
        "homllm.retrieval",
        "openai",
        "anthropic",
        "transformers",
    ]
    
    violations = []
    
    with open(applier_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
    except SyntaxError:
        pytest.fail("Applier has syntax error")
    
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


def test_no_forbidden_imports_in_diff():
    """Verify diff does not import from forbidden modules."""
    import ast
    from pathlib import Path
    
    diff_path = Path("src/homllm/context/diff.py")
    
    forbidden_patterns = [
        "homllm.intelligence",
        "homllm.generation",
        "homllm.retrieval",
    ]
    
    violations = []
    
    with open(diff_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
    except SyntaxError:
        pytest.fail("Diff has syntax error")
    
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


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_context():
    """Create mock ContextArtifact for testing."""
    from homllm.context.interfaces import ContextArtifact, ContextBlock
    
    blocks = (
        ContextBlock(
            block_id="block_1",
            file="test.py",
            start_line=1,
            end_line=5,
            content="def test_func():\n    pass",
            symbol_id="test_func",
            symbol_name="test_func",
            provenance=("retrieval",),
        ),
        ContextBlock(
            block_id="block_2",
            file="test.py",
            start_line=10,
            end_line=15,
            content="def helper():\n    return 42",
            symbol_id="helper",
            symbol_name="helper",
            provenance=("retrieval",),
        ),
        ContextBlock(
            block_id="block_3",
            file="utils.py",
            start_line=1,
            end_line=10,
            content="class Utils:\n    pass",
            symbol_id="Utils",
            symbol_name="Utils",
            provenance=("expansion",),
        ),
    )
    
    return ContextArtifact(
        query_id="test_query",
        context_text="def test_func():\n    pass\n\ndef helper():\n    return 42",
        blocks=blocks,
        token_budget=4000,
        used_tokens=50,
        provenance={"source": "test"},
        explain_trace=("Selected 3 blocks",),
    )


@pytest.fixture
def mock_empty_plan():
    """Create empty modification plan."""
    from homllm.intelligence.controller import ContextModificationPlan
    return ContextModificationPlan.empty()


@pytest.fixture
def mock_plan_with_drop():
    """Create plan with a DROP action."""
    from homllm.intelligence.controller import (
        ContextModificationPlan,
        UnifiedAction,
    )
    from homllm.intelligence.actions.level1.plan import (
        ContextModificationPlan as L1Plan,
    )
    from homllm.intelligence.actions.level2.plan import SemanticActionPlan
    from homllm.intelligence.actions.level3.plan import CognitiveActionPlan
    
    unified_actions = (
        UnifiedAction(
            level=1,
            action_type="DROP",
            target="block_2",
            priority=6,
            justification="High noise block",
            source_engine="level1",
            original_action=Mock(priority=6, justification="High noise block"),
        ),
    )
    
    return ContextModificationPlan(
        level1_plan=L1Plan.empty(),
        level2_plan=SemanticActionPlan.empty(),
        level3_plan=CognitiveActionPlan.empty(),
        unified_actions=unified_actions,
        diagnostics_available=True,
        levels_executed=(1,),
        total_actions=1,
    )


@pytest.fixture
def mock_plan_with_protect_and_drop():
    """Create plan with conflicting PROTECT and DROP."""
    from homllm.intelligence.controller import (
        ContextModificationPlan,
        UnifiedAction,
    )
    from homllm.intelligence.actions.level1.plan import (
        ContextModificationPlan as L1Plan,
    )
    from homllm.intelligence.actions.level2.plan import SemanticActionPlan
    from homllm.intelligence.actions.level3.plan import CognitiveActionPlan
    
    unified_actions = (
        UnifiedAction(
            level=1,
            action_type="PROTECT",
            target="block_1",
            priority=1,
            justification="Core definition",
            source_engine="level1",
            original_action=Mock(priority=1, justification="Core definition"),
        ),
        UnifiedAction(
            level=2,
            action_type="DROP",
            target="block_1",
            priority=6,
            justification="Trying to drop protected block",
            source_engine="level2",
            original_action=Mock(priority=6, justification="Trying to drop"),
        ),
    )
    
    return ContextModificationPlan(
        level1_plan=L1Plan.empty(),
        level2_plan=SemanticActionPlan.empty(),
        level3_plan=CognitiveActionPlan.empty(),
        unified_actions=unified_actions,
        diagnostics_available=True,
        levels_executed=(1, 2),
        total_actions=2,
    )


# =============================================================================
# DIFF TESTS
# =============================================================================

def test_diff_entry_frozen():
    """Verify DiffEntry is immutable."""
    from homllm.context.diff import DiffEntry
    
    entry = DiffEntry(
        change_type="removed",
        target="block_1",
        level=1,
        action_type="DROP",
        reason="Test",
    )
    
    with pytest.raises(Exception):
        entry.target = "modified"


def test_context_diff_empty():
    """Verify empty ContextDiff creation."""
    from homllm.context.diff import ContextDiff
    
    diff = ContextDiff.empty()
    
    assert diff.is_empty
    assert diff.total_changes == 0
    assert len(diff.entries) == 0


def test_diff_builder():
    """Verify DiffBuilder produces correct ContextDiff."""
    from homllm.context.diff import DiffBuilder
    
    builder = DiffBuilder()
    builder.add_entry(
        change_type="removed",
        target="block_1",
        level=1,
        action_type="DROP",
        reason="Test removal",
    )
    builder.add_entry(
        change_type="protected",
        target="block_2",
        level=1,
        action_type="PROTECT",
        reason="Test protection",
    )
    
    diff = builder.build()
    
    assert len(diff.entries) == 2
    assert diff.blocks_removed == 1
    assert diff.blocks_protected == 1


def test_diff_to_dict():
    """Verify diff serializes to JSON-compatible dict."""
    from homllm.context.diff import DiffBuilder
    import json
    
    builder = DiffBuilder()
    builder.add_entry("removed", "block_1", 1, "DROP", "Test")
    diff = builder.build()
    
    diff_dict = diff.to_dict()
    json_str = json.dumps(diff_dict)
    
    assert json_str
    assert "entries" in diff_dict
    assert "summary" in diff_dict


# =============================================================================
# APPLIER TESTS
# =============================================================================

def test_empty_plan_returns_unchanged_context(mock_context, mock_empty_plan):
    """Verify empty plan returns context unchanged."""
    from homllm.context.applier import ContextApplier
    
    applier = ContextApplier()
    result = applier.apply(mock_empty_plan, mock_context)
    
    assert result.success
    assert result.context.blocks == mock_context.blocks
    assert result.diff.is_empty


def test_context_not_mutated(mock_context, mock_plan_with_drop):
    """Verify original context is never mutated."""
    from homllm.context.applier import ContextApplier
    
    original_blocks = mock_context.blocks
    original_query_id = mock_context.query_id
    
    applier = ContextApplier()
    result = applier.apply(mock_plan_with_drop, mock_context)
    
    # Original context unchanged
    assert mock_context.blocks == original_blocks
    assert mock_context.query_id == original_query_id
    
    # New context is different
    assert len(result.context.blocks) < len(mock_context.blocks)


def test_drop_action_removes_block(mock_context, mock_plan_with_drop):
    """Verify DROP action removes the specified block."""
    from homllm.context.applier import ContextApplier
    
    applier = ContextApplier()
    result = applier.apply(mock_plan_with_drop, mock_context)
    
    # block_2 should be removed
    block_ids = [b.block_id for b in result.context.blocks]
    assert "block_2" not in block_ids
    assert "block_1" in block_ids
    assert "block_3" in block_ids
    
    # Diff should record the removal
    assert result.diff.blocks_removed == 1


def test_protect_prevents_drop(mock_context, mock_plan_with_protect_and_drop):
    """Verify PROTECT action prevents DROP."""
    from homllm.context.applier import ContextApplier
    
    applier = ContextApplier()
    result = applier.apply(mock_plan_with_protect_and_drop, mock_context)
    
    # block_1 should NOT be removed (protected)
    block_ids = [b.block_id for b in result.context.blocks]
    assert "block_1" in block_ids
    
    # Should have recorded a conflict
    assert len(result.diff.conflicts) > 0


def test_applier_determinism(mock_context, mock_plan_with_drop):
    """Verify same input produces same output."""
    from homllm.context.applier import ContextApplier
    
    applier = ContextApplier()
    
    result1 = applier.apply(mock_plan_with_drop, mock_context)
    result2 = applier.apply(mock_plan_with_drop, mock_context)
    
    # Same blocks
    assert len(result1.context.blocks) == len(result2.context.blocks)
    for b1, b2 in zip(result1.context.blocks, result2.context.blocks):
        assert b1.block_id == b2.block_id
    
    # Same diff
    assert len(result1.diff.entries) == len(result2.diff.entries)


def test_diff_completeness(mock_context, mock_plan_with_drop):
    """Verify every action produces a diff entry."""
    from homllm.context.applier import ContextApplier
    
    applier = ContextApplier()
    result = applier.apply(mock_plan_with_drop, mock_context)
    
    # Should have at least one entry for the DROP action
    assert len(result.diff.entries) >= 1


def test_factory_function():
    """Verify factory function creates applier."""
    from homllm.context.applier import create_context_applier
    
    applier = create_context_applier(
        enforce_token_budget=True,
        allow_empty_context=False,
    )
    
    assert applier is not None
    assert applier.config.enforce_token_budget is True
    assert applier.config.allow_empty_context is False


def test_applier_result_frozen():
    """Verify ApplierResult is immutable."""
    from homllm.context.applier import ApplierResult
    from homllm.context.diff import ContextDiff
    from homllm.context.interfaces import ContextArtifact
    
    result = ApplierResult(
        context=ContextArtifact(
            query_id="test",
            context_text="",
            blocks=(),
            token_budget=100,
            used_tokens=0,
            provenance={},
            explain_trace=(),
        ),
        diff=ContextDiff.empty(),
        success=True,
    )
    
    with pytest.raises(Exception):
        result.success = False
