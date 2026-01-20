"""Import boundary tests for Ranking layer."""

import ast
from pathlib import Path


def get_imports(module_path: Path) -> list[str]:
    """Extract all import statements from a Python module."""
    imports = []
    with open(module_path, "r") as f:
        tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
    return imports


def test_no_ranking_imports_from_later_phases():
    """
    Test that Ranking layer does not import from later phases.
    
    INV-005: No layer may import from a later phase.
    """
    ranking_dir = Path("src/homllm/ranking")
    forbidden_modules = [
        "homllm.context",
        "homllm.generation",
        "homllm.evaluation",
    ]

    violations = []
    for py_file in ranking_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        imports = get_imports(py_file)
        for imp in imports:
            for forbidden in forbidden_modules:
                if imp.startswith(forbidden):
                    violations.append(f"{py_file}: imports {imp}")

    assert not violations, f"Import violations found:\n" + "\n".join(violations)


def test_no_generation_imports_in_ranking():
    """
    Test that Ranking does not import generation modules.
    
    RNK-003: Does not call generation
    """
    ranking_dir = Path("src/homllm/ranking")
    forbidden = "homllm.generation"

    violations = []
    for py_file in ranking_dir.rglob("*.py"):
        imports = get_imports(py_file)
        for imp in imports:
            if imp.startswith(forbidden):
                violations.append(f"{py_file}: imports {imp}")

    assert not violations, f"Generation imports found:\n" + "\n".join(violations)


def test_no_evaluation_imports_in_ranking():
    """
    Test that Ranking does not import evaluation modules.
    
    RNK-003: Does not call generation or evaluation
    """
    ranking_dir = Path("src/homllm/ranking")
    forbidden = "homllm.evaluation"

    violations = []
    for py_file in ranking_dir.rglob("*.py"):
        imports = get_imports(py_file)
        for imp in imports:
            if imp.startswith(forbidden):
                violations.append(f"{py_file}: imports {imp}")

    assert not violations, f"Evaluation imports found:\n" + "\n".join(violations)
