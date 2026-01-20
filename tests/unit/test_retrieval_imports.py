"""Import boundary tests for Retrieval layer."""

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


def test_no_retrieval_imports_from_later_phases():
    """
    Test that Retrieval layer does not import from later phases.
    
    INV-005: No layer may import from a later phase.
    """
    retrieval_dir = Path("src/homllm/retrieval")
    forbidden_modules = [
        "homllm.ranking",
        "homllm.context",
        "homllm.generation",
        "homllm.evaluation",
    ]

    violations = []
    for py_file in retrieval_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        imports = get_imports(py_file)
        for imp in imports:
            for forbidden in forbidden_modules:
                if imp.startswith(forbidden):
                    violations.append(f"{py_file}: imports {imp}")

    assert not violations, f"Import violations found:\n" + "\n".join(violations)


def test_no_generation_imports_in_retrieval():
    """
    Test that Retrieval does not import generation modules.
    
    RET-005: MUST NOT call generation or evaluation modules.
    """
    retrieval_dir = Path("src/homllm/retrieval")
    forbidden = "homllm.generation"

    violations = []
    for py_file in retrieval_dir.rglob("*.py"):
        imports = get_imports(py_file)
        for imp in imports:
            if imp.startswith(forbidden):
                violations.append(f"{py_file}: imports {imp}")

    assert not violations, f"Generation imports found:\n" + "\n".join(violations)


def test_no_evaluation_imports_in_retrieval():
    """
    Test that Retrieval does not import evaluation modules.
    
    RET-005: MUST NOT call generation or evaluation modules.
    """
    retrieval_dir = Path("src/homllm/retrieval")
    forbidden = "homllm.evaluation"

    violations = []
    for py_file in retrieval_dir.rglob("*.py"):
        imports = get_imports(py_file)
        for imp in imports:
            if imp.startswith(forbidden):
                violations.append(f"{py_file}: imports {imp}")

    assert not violations, f"Evaluation imports found:\n" + "\n".join(violations)
