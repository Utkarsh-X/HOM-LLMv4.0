import ast
from pathlib import Path

FORBIDDEN_PREFIXES = (
    "homllm.retrieval",
    "homllm.ranking",
    "homllm.context",
    "homllm.indexer",
)

SCANNED_DIRS = (
    "services",
    "contracts",
    "registry",
    "ledger",
    "artifacts",
    "serialization",
    "app",
    "runtime",
)


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_v3_imports_are_forbidden_outside_adapters() -> None:
    root = Path("src/homllm_v4")
    violations: list[str] = []
    for dirname in SCANNED_DIRS:
        directory = root / dirname
        if not directory.exists():
            continue
        for path in directory.rglob("*.py"):
            for module in imported_modules(path):
                if module.startswith(FORBIDDEN_PREFIXES):
                    violations.append(f"{path}: {module}")

    assert violations == []


def test_adapter_shells_are_present() -> None:
    root = Path("src/homllm_v4/adapters")

    assert (root / "v3_index_adapter.py").is_file()
    assert (root / "v3_retrieval_adapter.py").is_file()
    assert (root / "v3_ranking_adapter.py").is_file()
    assert (root / "v3_context_adapter.py").is_file()
