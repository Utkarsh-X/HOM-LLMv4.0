"""Import boundary tests for Context layer."""

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


def test_no_context_imports_from_later_phases():
    """
    Test that Context layer does not import from later phases.
    
    INV-005: No layer may import from a later phase.
    """
    context_dir = Path("src/homllm/context")
    forbidden_modules = [
        "homllm.generation",
        "homllm.evaluation",
    ]

    violations = []
    for py_file in context_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        imports = get_imports(py_file)
        for imp in imports:
            for forbidden in forbidden_modules:
                if imp.startswith(forbidden):
                    violations.append(f"{py_file}: imports {imp}")

    assert not violations, f"Import violations found:\n" + "\n".join(violations)


def test_no_generation_imports_in_context():
    """
    Test that Context does not import generation modules.
    
    CTX-004: MUST NOT call LLM for scoring
    """
    context_dir = Path("src/homllm/context")
    forbidden = "homllm.generation"

    violations = []
    for py_file in context_dir.rglob("*.py"):
        imports = get_imports(py_file)
        for imp in imports:
            if imp.startswith(forbidden):
                violations.append(f"{py_file}: imports {imp}")

    assert not violations, f"Generation imports found:\n" + "\n".join(violations)


def test_no_evaluation_imports_in_context():
    """
    Test that Context does not import evaluation modules.
    """
    context_dir = Path("src/homllm/context")
    forbidden = "homllm.evaluation"

    violations = []
    for py_file in context_dir.rglob("*.py"):
        imports = get_imports(py_file)
        for imp in imports:
            if imp.startswith(forbidden):
                violations.append(f"{py_file}: imports {imp}")

    assert not violations, f"Evaluation imports found:\n" + "\n".join(violations)
