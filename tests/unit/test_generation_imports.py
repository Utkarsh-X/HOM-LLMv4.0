"""Import boundary tests for Generation layer."""

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


def test_no_generation_imports_from_retrieval_ranking():
    """
    Test that Generation layer does not import from retrieval or ranking.
    
    GEN-004: No retrieval or ranking logic
    """
    generation_dir = Path("src/homllm/generation")
    forbidden_modules = [
        "homllm.retrieval",
        "homllm.ranking",
    ]

    violations = []
    for py_file in generation_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        imports = get_imports(py_file)
        for imp in imports:
            for forbidden in forbidden_modules:
                if imp.startswith(forbidden):
                    violations.append(f"{py_file}: imports {imp}")

    assert not violations, f"Import violations found:\n" + "\n".join(violations)


def test_no_evaluation_imports_in_generation():
    """
    Test that Generation does not import evaluation modules.
    """
    generation_dir = Path("src/homllm/generation")
    forbidden = "homllm.evaluation"

    violations = []
    for py_file in generation_dir.rglob("*.py"):
        imports = get_imports(py_file)
        for imp in imports:
            if imp.startswith(forbidden):
                violations.append(f"{py_file}: imports {imp}")

    assert not violations, f"Evaluation imports found:\n" + "\n".join(violations)
