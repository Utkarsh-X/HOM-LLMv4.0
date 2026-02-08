"""Unit tests for LanceDBAdapter behavior."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest

from homllm.common.types import Document, Vector


@dataclass
class _FakeEmbedder:
    dimension: int = 4

    def embed_code(self, text: str) -> Vector:
        # Deterministic small vector.
        return Vector(values=(0.0, 0.1, 0.2, 0.3))


def _tmp_dir() -> Path:
    path = Path("artifacts") / "test_tmp" / "lancedb_adapter"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_index_opens_existing_table_when_handle_missing():
    """
    Regression: indexing should not fail if table exists but `_table` is None.

    This can happen after reconnect/reset cycles in long-running indexing.
    """
    from homllm.indexer.storage.lancedb_adapter import LanceDBAdapter

    db_path = _tmp_dir() / uuid4().hex
    embedder = _FakeEmbedder()
    adapter = LanceDBAdapter(db_path, embedder)
    adapter.connect()

    docs = [Document(doc_id="d1", content="x", metadata={"a": "b"})]
    adapter.index(iter(docs))

    # Simulate stale handle even though table exists.
    adapter._table = None  # type: ignore[attr-defined]

    # Must append, not attempt create_table.
    adapter.index(iter([Document(doc_id="d2", content="y", metadata={"c": "d"})]))

    # Sanity: table exists and has at least 2 rows.
    assert adapter.db is not None
    tables_resp = adapter.db.list_tables()
    table_names = getattr(tables_resp, "tables", tables_resp)
    assert adapter.table_name in table_names
    table = adapter.db.open_table(adapter.table_name)
    assert table.count_rows() >= 2


def test_connect_opens_existing_table_handle():
    """Regression: connect() must open existing table for read/search paths."""
    from homllm.indexer.storage.lancedb_adapter import LanceDBAdapter

    db_path = _tmp_dir() / uuid4().hex
    embedder = _FakeEmbedder()

    writer = LanceDBAdapter(db_path, embedder)
    writer.connect()
    writer.index(iter([Document(doc_id="d1", content="x", metadata={"a": "b"})]))

    reader = LanceDBAdapter(db_path, embedder)
    reader.connect()

    assert reader._table is not None  # Existing table should be opened.
