"""Unit tests for context block assembler."""

from homllm.context.assembler import BlockAssembler
from homllm.retrieval.interfaces import Candidate


def test_assembler_handles_none_symbol_id():
    """Assembler should not crash when symbol_id is missing."""
    assembler = BlockAssembler()
    candidates = [
        Candidate(
            doc_id="chunk:a",
            file="pkg/a.py",
            symbol_id=None,
            content="def f():\n    return 1\n",
            provenance=("bm25",),
        )
    ]

    blocks = assembler.assemble(candidates)
    assert len(blocks) == 1
    assert blocks[0].symbol_id is None
    assert blocks[0].start_line == 1
    assert blocks[0].end_line >= 1
