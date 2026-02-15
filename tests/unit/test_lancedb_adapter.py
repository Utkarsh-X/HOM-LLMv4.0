"""Unit tests for LanceDBAdapter behavior."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from uuid import uuid4

import pytest

from homllm.common.types import Document, Vector
from homllm.retrieval.interfaces import RetrievalConfig


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


def test_distance_to_similarity_modes_are_bounded_and_monotonic():
    """Calibration policies must be deterministic, monotonic, and bounded."""
    from homllm.indexer.storage.lancedb_adapter import LanceDBAdapter

    distances = [0.0, 0.1, 0.5, 1.0, 3.0, 10.0]
    for mode in ("legacy", "calibrated_v1"):
        sims = [
            LanceDBAdapter._distance_to_similarity(d, calibration_mode=mode)
            for d in distances
        ]
        assert all(0.0 <= s <= 1.0 for s in sims)
        assert math.isclose(sims[0], 1.0, rel_tol=0.0, abs_tol=1e-12)
        for left, right in zip(sims, sims[1:]):
            assert left >= right


def test_distance_to_similarity_rejects_unknown_mode():
    from homllm.indexer.storage.lancedb_adapter import LanceDBAdapter

    with pytest.raises(ValueError, match="Unknown vector calibration mode"):
        LanceDBAdapter._distance_to_similarity(0.25, calibration_mode="unknown_mode")


def test_retrieval_config_rejects_unknown_vector_calibration_mode():
    with pytest.raises(ValueError, match="retrieval.vector.calibration_mode"):
        RetrievalConfig(
            bm25_top_k=10,
            vector_top_k=10,
            hybrid_method="rrf",
            rrf_k=10,
            bm25_weight=0.5,
            vector_weight=0.5,
            expansion_enabled=True,
            expansion_max_additions=4,
            expansion_min_similarity=0.25,
            vector_calibration_mode="invalid_mode",
        )
