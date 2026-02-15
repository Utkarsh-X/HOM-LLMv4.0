"""Unit tests for deterministic chunk_max_lines enforcement."""

from homllm.common.config import HierarchicalChunkingConfig
from homllm.common.types import SymbolInfo, SymbolKind
from homllm.indexer.hierarchical_chunker import HierarchicalChunker


def _line_count(text: str) -> int:
    return len(text.split("\n")) if text else 0


def test_fine_chunk_max_lines_enforced_with_lossless_span_coverage():
    chunker = HierarchicalChunker(
        HierarchicalChunkingConfig(
            enabled=True,
            fine_enabled=True,
            medium_enabled=False,
            coarse_enabled=False,
            chunk_max_lines=6,
        )
    )
    code = (
        "class Handler:\n"
        "    def process(self):\n"
        "        a = 1\n"
        "        b = 2\n"
        "        c = 3\n"
        "        d = 4\n"
        "        e = 5\n"
        "        f = 6\n"
        "        return f\n"
    )
    symbols = [
        SymbolInfo(
            id="sym:handler",
            name="Handler",
            kind=SymbolKind.CLASS,
            file="pkg/handler.py",
            start_line=1,
            end_line=1,
        ),
        SymbolInfo(
            id="sym:process",
            name="process",
            kind=SymbolKind.FUNCTION,
            file="pkg/handler.py",
            start_line=2,
            end_line=9,
            signature="process(self)",
            parent_id="sym:handler",
        ),
    ]

    chunks = chunker.create_chunks("pkg/handler.py", code, symbols, [])
    fine_chunks = [c for c in chunks if c.granularity_level == "fine"]

    assert len(fine_chunks) == 3
    assert [(c.span_start, c.span_end) for c in fine_chunks] == [(2, 4), (5, 7), (8, 9)]
    assert all(_line_count(c.content) <= 6 for c in fine_chunks)


def test_medium_chunk_max_lines_enforced_with_lossless_span_coverage():
    chunker = HierarchicalChunker(
        HierarchicalChunkingConfig(
            enabled=True,
            fine_enabled=False,
            medium_enabled=True,
            coarse_enabled=False,
            chunk_max_lines=4,
        )
    )
    code = (
        "def one():\n"
        "    x = 1\n"
        "    return x\n"
        "\n"
        "def two():\n"
        "    y = 2\n"
        "    z = 3\n"
        "    return y + z\n"
    )
    symbols = [
        SymbolInfo(
            id="sym:one",
            name="one",
            kind=SymbolKind.FUNCTION,
            file="pkg/mod.py",
            start_line=1,
            end_line=3,
            signature="one()",
        ),
        SymbolInfo(
            id="sym:two",
            name="two",
            kind=SymbolKind.FUNCTION,
            file="pkg/mod.py",
            start_line=5,
            end_line=8,
            signature="two()",
        ),
    ]

    chunks = chunker.create_chunks("pkg/mod.py", code, symbols, [])
    medium_chunks = [c for c in chunks if c.granularity_level == "medium"]

    assert [(c.span_start, c.span_end) for c in medium_chunks] == [(1, 4), (5, 8)]
    assert all(_line_count(c.content) <= 4 for c in medium_chunks)


def test_coarse_chunk_max_lines_enforced_and_chunk_ids_deterministic():
    chunker = HierarchicalChunker(
        HierarchicalChunkingConfig(
            enabled=True,
            fine_enabled=False,
            medium_enabled=False,
            coarse_enabled=True,
            chunk_max_lines=3,
        )
    )
    code = (
        "\"\"\"module doc\"\"\"\n"
        "def a():\n"
        "    pass\n"
        "def b():\n"
        "    pass\n"
        "def c():\n"
        "    pass\n"
        "def d():\n"
        "    pass\n"
        "def e():\n"
        "    pass\n"
        "def f():\n"
        "    pass\n"
    )
    symbols = [
        SymbolInfo(
            id=f"sym:{name}",
            name=name,
            kind=SymbolKind.FUNCTION,
            file="pkg/coarse.py",
            start_line=(idx * 2) + 2,
            end_line=(idx * 2) + 3,
            signature=f"{name}()",
        )
        for idx, name in enumerate(["a", "b", "c", "d", "e", "f"])
    ]

    first = chunker.create_chunks("pkg/coarse.py", code, symbols, [])
    second = chunker.create_chunks("pkg/coarse.py", code, symbols, [])
    first_ids = [c.chunk_id for c in first]
    second_ids = [c.chunk_id for c in second]

    assert first_ids == second_ids
    assert len(first) == 3
    assert all(c.granularity_level == "coarse" for c in first)
    assert all(_line_count(c.content) <= 3 for c in first)
