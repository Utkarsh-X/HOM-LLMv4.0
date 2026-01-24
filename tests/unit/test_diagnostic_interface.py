"""
Unit tests for Diagnostic Engine Interface.

Tests:
1. Snapshot structure validity
2. Explicit unavailable status for failures
3. Import boundary checks
4. Determinism
"""

import ast
import sys
from pathlib import Path
from dataclasses import dataclass

import pytest


# =============================================================================
# IMPORT TESTS
# =============================================================================

def test_interface_imports_succeed():
    """Verify that interface imports work correctly."""
    from homllm.intelligence.interfaces import (
        StructuralDiagnostics,
        SemanticDiagnostics,
        CognitiveDiagnostics,
        DiagnosticSnapshot,
        DiagnosticProvider,
    )
    
    # Verify all are importable
    assert StructuralDiagnostics is not None
    assert SemanticDiagnostics is not None
    assert CognitiveDiagnostics is not None
    assert DiagnosticSnapshot is not None
    assert DiagnosticProvider is not None


def test_controller_imports_succeed():
    """Verify that controller imports work correctly."""
    from homllm.intelligence.diagnostics.controller import (
        DiagnosticController,
        create_diagnostic_provider,
    )
    
    assert DiagnosticController is not None
    assert create_diagnostic_provider is not None


def test_no_action_engine_imports():
    """
    Verify interface does not import from action engines or later phases.
    
    The interface must be agnostic to its consumers.
    """
    interface_path = Path("src/homllm/intelligence/interfaces.py")
    controller_path = Path("src/homllm/intelligence/diagnostics/controller.py")
    
    forbidden_patterns = [
        "homllm.intelligence.actions",
        "homllm.generation",
        "homllm.evaluation",
    ]
    
    def check_imports(file_path: Path) -> list[str]:
        violations = []
        if not file_path.exists():
            return violations
            
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return violations
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_patterns:
                        if alias.name.startswith(forbidden):
                            violations.append(f"{file_path}: imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_patterns:
                        if node.module.startswith(forbidden):
                            violations.append(f"{file_path}: imports {node.module}")
        
        return violations
    
    violations = check_imports(interface_path) + check_imports(controller_path)
    assert not violations, f"Forbidden imports found:\n" + "\n".join(violations)


# =============================================================================
# STRUCTURE TESTS
# =============================================================================

def test_snapshot_structure():
    """Verify DiagnosticSnapshot has all required levels."""
    from homllm.intelligence.interfaces import (
        DiagnosticSnapshot,
        StructuralDiagnostics,
        SemanticDiagnostics,
        CognitiveDiagnostics,
    )
    
    # Create unavailable levels for testing
    l1 = StructuralDiagnostics(
        status="unavailable",
        reason="test",
        blocks=(),
        result=None,
    )
    l2 = SemanticDiagnostics(
        status="unavailable",
        reason="test",
        result=None,
    )
    l3 = CognitiveDiagnostics(
        status="unavailable",
        reason="test",
        result=None,
    )
    
    snapshot = DiagnosticSnapshot(level1=l1, level2=l2, level3=l3)
    
    # Verify structure
    assert hasattr(snapshot, "level1")
    assert hasattr(snapshot, "level2")
    assert hasattr(snapshot, "level3")
    
    assert isinstance(snapshot.level1, StructuralDiagnostics)
    assert isinstance(snapshot.level2, SemanticDiagnostics)
    assert isinstance(snapshot.level3, CognitiveDiagnostics)


def test_containers_are_frozen():
    """Verify all containers are immutable (frozen dataclasses)."""
    from homllm.intelligence.interfaces import (
        DiagnosticSnapshot,
        StructuralDiagnostics,
        SemanticDiagnostics,
        CognitiveDiagnostics,
    )
    
    l1 = StructuralDiagnostics(status="unavailable", reason="test")
    l2 = SemanticDiagnostics(status="unavailable", reason="test")
    l3 = CognitiveDiagnostics(status="unavailable", reason="test")
    snapshot = DiagnosticSnapshot(level1=l1, level2=l2, level3=l3)
    
    # Verify frozen (should raise FrozenInstanceError)
    with pytest.raises(Exception):  # FrozenInstanceError
        l1.status = "available"
    
    with pytest.raises(Exception):
        l2.status = "available"
    
    with pytest.raises(Exception):
        l3.status = "available"
    
    with pytest.raises(Exception):
        snapshot.level1 = l2  # type: ignore


def test_unavailable_status_explicit():
    """Verify unavailable status includes explicit reason."""
    from homllm.intelligence.interfaces import StructuralDiagnostics
    
    # Unavailable must have a reason
    diag = StructuralDiagnostics(
        status="unavailable",
        reason="L1 analysis failed: ValueError: no blocks",
    )
    
    assert diag.status == "unavailable"
    assert len(diag.reason) > 0
    assert "failed" in diag.reason.lower() or "no blocks" in diag.reason.lower()


def test_all_available_property():
    """Verify all_available property works correctly."""
    from homllm.intelligence.interfaces import (
        DiagnosticSnapshot,
        StructuralDiagnostics,
        SemanticDiagnostics,
        CognitiveDiagnostics,
    )
    
    # All unavailable
    snapshot_none = DiagnosticSnapshot(
        level1=StructuralDiagnostics(status="unavailable", reason="test"),
        level2=SemanticDiagnostics(status="unavailable", reason="test"),
        level3=CognitiveDiagnostics(status="unavailable", reason="test"),
    )
    assert snapshot_none.all_available is False
    assert snapshot_none.any_unavailable is True
    
    # All available
    snapshot_all = DiagnosticSnapshot(
        level1=StructuralDiagnostics(status="available", reason=""),
        level2=SemanticDiagnostics(status="available", reason=""),
        level3=CognitiveDiagnostics(status="available", reason=""),
    )
    assert snapshot_all.all_available is True
    assert snapshot_all.any_unavailable is False


# =============================================================================
# CONTROLLER TESTS
# =============================================================================

def test_controller_with_empty_context():
    """Verify controller handles empty context gracefully."""
    from homllm.context.interfaces import ContextArtifact
    from homllm.intelligence.diagnostics.controller import DiagnosticController
    
    controller = DiagnosticController()
    
    # Create an empty context
    context = ContextArtifact(
        query_id="test_query",
        context_text="",
        blocks=(),
        token_budget=4000,
        used_tokens=0,
        provenance={},
        explain_trace=(),
    )
    
    snapshot = controller.analyze(context)
    
    # L1 should be unavailable (no blocks)
    assert snapshot.level1.status == "unavailable"
    assert "no blocks" in snapshot.level1.reason.lower()
    
    # L2 and L3 should also be unavailable (depend on L1)
    assert snapshot.level2.status == "unavailable"
    assert snapshot.level3.status == "unavailable"


def test_controller_determinism():
    """Verify controller produces deterministic output."""
    from homllm.context.interfaces import ContextArtifact, ContextBlock
    from homllm.intelligence.diagnostics.controller import DiagnosticController
    
    controller = DiagnosticController()
    
    # Create a simple context with one block
    block = ContextBlock(
        block_id="test_block_1",
        file="test.py",
        start_line=1,
        end_line=5,
        content="def foo():\n    return 42\n",
        symbol_id="foo",
        symbol_name="foo",
        provenance=("test",),
    )
    
    context = ContextArtifact(
        query_id="What does foo do?",
        context_text="def foo():\n    return 42\n",
        blocks=(block,),
        token_budget=4000,
        used_tokens=10,
        provenance={"query": "What does foo do?"},
        explain_trace=(),
    )
    
    # Run twice
    snapshot1 = controller.analyze(context)
    snapshot2 = controller.analyze(context)
    
    # Verify determinism (same status at minimum)
    assert snapshot1.level1.status == snapshot2.level1.status
    assert snapshot1.level2.status == snapshot2.level2.status
    assert snapshot1.level3.status == snapshot2.level3.status
    
    # If available, verify same block count
    if snapshot1.level1.status == "available":
        assert len(snapshot1.level1.blocks) == len(snapshot2.level1.blocks)
