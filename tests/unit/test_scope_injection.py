"""Unit tests for scope-aware fine chunking."""

from homllm.common.config import HierarchicalChunkingConfig
from homllm.common.types import SymbolInfo, SymbolKind
from homllm.indexer.hierarchical_chunker import HierarchicalChunker


def _chunker() -> HierarchicalChunker:
    return HierarchicalChunker(
        HierarchicalChunkingConfig(
            enabled=True,
            fine_enabled=True,
            medium_enabled=False,
            coarse_enabled=False,
        )
    )


def _find_fine_chunk(chunks, span_start: int):
    for chunk in chunks:
        if chunk.granularity_level == "fine" and chunk.span_start == span_start:
            return chunk
    return None


def test_method_chunk_includes_class_scope_and_file_header():
    code = (
        "class PaymentController:\n"
        "    def validate(self):\n"
        "        status = self.status\n"
        "        return self.status == 'OK'\n"
    )
    class_id = "sym:PaymentController"
    method_id = "sym:validate"
    symbols = [
        SymbolInfo(
            id=class_id,
            name="PaymentController",
            kind=SymbolKind.CLASS,
            file="controllers/payment_controller.py",
            start_line=1,
            end_line=4,
        ),
        SymbolInfo(
            id=method_id,
            name="validate",
            kind=SymbolKind.FUNCTION,
            file="controllers/payment_controller.py",
            start_line=2,
            end_line=4,
            signature="validate(self)",
            parent_id=class_id,
        ),
    ]

    chunks = _chunker().create_chunks(
        "controllers/payment_controller.py",
        code,
        symbols,
        [],
    )
    method_chunk = _find_fine_chunk(chunks, span_start=2)

    assert method_chunk is not None
    assert method_chunk.content.startswith("# File: controllers/payment_controller.py")
    assert "class PaymentController:" in method_chunk.content
    assert "\n    def validate(self):" in method_chunk.content
    assert "\n        return self.status == 'OK'" in method_chunk.content


def test_nested_function_chunk_includes_parent_function_scope():
    code = (
        "def outer():\n"
        "    def inner():\n"
        "        value = 42\n"
        "        return value\n"
        "    return inner()\n"
    )
    outer_id = "sym:outer"
    inner_id = "sym:inner"
    symbols = [
        SymbolInfo(
            id=outer_id,
            name="outer",
            kind=SymbolKind.FUNCTION,
            file="nested.py",
            start_line=1,
            end_line=5,
            signature="outer()",
        ),
        SymbolInfo(
            id=inner_id,
            name="inner",
            kind=SymbolKind.FUNCTION,
            file="nested.py",
            start_line=2,
            end_line=4,
            signature="inner()",
            parent_id=outer_id,
        ),
    ]

    chunks = _chunker().create_chunks("nested.py", code, symbols, [])
    inner_chunk = _find_fine_chunk(chunks, span_start=2)

    assert inner_chunk is not None
    assert "def outer():" in inner_chunk.content
    assert "\n    def inner():" in inner_chunk.content
    assert "\n        return value" in inner_chunk.content


def test_module_level_function_chunk_has_no_extra_scope_indentation():
    code = (
        "def standalone():\n"
        "    value = 'ok'\n"
        "    return value\n"
    )
    symbols = [
        SymbolInfo(
            id="sym:standalone",
            name="standalone",
            kind=SymbolKind.FUNCTION,
            file="module.py",
            start_line=1,
            end_line=3,
            signature="standalone()",
        )
    ]

    chunks = _chunker().create_chunks("module.py", code, symbols, [])
    chunk = _find_fine_chunk(chunks, span_start=1)

    assert chunk is not None
    lines = chunk.content.split("\n")
    function_line = [line for line in lines if "def standalone():" in line][0]
    assert not function_line.startswith("    ")
