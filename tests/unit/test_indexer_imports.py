"""Import boundary tests for Indexer layer."""

import ast
import importlib.util
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


def test_no_indexer_imports_from_later_phases():
    """
    Test that Indexer layer does not import from later phases.
    
    INV-005: No layer may import from a later phase.
    """
    indexer_dir = Path("src/homllm/indexer")
    forbidden_modules = [
        "homllm.retrieval",
        "homllm.ranking",
        "homllm.context",
        "homllm.generation",
        "homllm.evaluation",
    ]

    violations = []
    for py_file in indexer_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        imports = get_imports(py_file)
        for imp in imports:
            for forbidden in forbidden_modules:
                if imp.startswith(forbidden):
                    violations.append(f"{py_file}: imports {imp}")

    assert not violations, f"Import violations found:\n" + "\n".join(violations)


def test_no_llm_api_imports_in_indexer():
    """
    Test that Indexer does not import LLM APIs.
    
    IDX-002: No network calls during indexing.
    """
    indexer_dir = Path("src/homllm/indexer")
    forbidden_modules = [
        "openai",
        "anthropic",
        "google.generativeai",
        "requests",
        "httpx",
    ]

    violations = []
    for py_file in indexer_dir.rglob("*.py"):
        imports = get_imports(py_file)
        for imp in imports:
            for forbidden in forbidden_modules:
                if imp.startswith(forbidden):
                    violations.append(f"{py_file}: imports {imp}")

    assert not violations, f"LLM API imports found:\n" + "\n".join(violations)


def test_no_evaluation_imports_in_indexer():
    """
    Test that Indexer does not import evaluation modules.
    
    INV-005: Evaluation code has zero imports from core pipeline.
    """
    indexer_dir = Path("src/homllm/indexer")
    forbidden = "homllm.evaluation"

    violations = []
    for py_file in indexer_dir.rglob("*.py"):
        imports = get_imports(py_file)
        for imp in imports:
            if imp.startswith(forbidden):
                violations.append(f"{py_file}: imports {imp}")

    assert not violations, f"Evaluation imports found:\n" + "\n".join(violations)
