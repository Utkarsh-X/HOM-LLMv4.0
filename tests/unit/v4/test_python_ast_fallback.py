import importlib
import sys
from pathlib import Path

import pytest

from homllm.indexer.parser import _PythonAstParser


def _block_tree_sitter_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force ``import tree_sitter`` to raise ImportError."""
    import builtins

    real_import = builtins.__import__

    def guarded(name: str, *args: object, **kwargs: object) -> object:
        if name == "tree_sitter":
            raise ImportError("tree_sitter blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


def test_parser_module_imports_and_falls_back_when_tree_sitter_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _block_tree_sitter_import(monkeypatch)
    monkeypatch.delitem(sys.modules, "homllm.indexer.parser", raising=False)

    fresh = importlib.import_module("homllm.indexer.parser")

    assert fresh.TREE_SITTER_AVAILABLE is False
    assert fresh.Node is None

    parser = fresh.TreeSitterParser()
    assert isinstance(parser.parsers["python"], fresh._PythonAstParser)

    source = tmp_path / "dummy.py"
    source.write_text("VALUE = 1\n\ndef load():\n    return VALUE\n", encoding="utf-8")
    result = parser.parse(source, "python")
    assert result.parse_error is False
    assert any(symbol.name == "load" for symbol in result.symbols)


def test_python_ast_fallback_links_parent_nodes_for_indexing_consumers() -> None:
    tree = _PythonAstParser().parse(
        b"VALUE = 1\n\n\ndef load():\n    return VALUE\n"
    )

    module = tree.root_node
    assert module.children

    for child in module.children:
        assert child.parent is module

    function = next(child for child in module.children if child.type == "function_definition")
    body = function.child_by_field_name("body")
    assert body is not None
    assert function.parent is module
    assert body.parent is function
