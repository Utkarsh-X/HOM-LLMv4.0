"""Unit tests for retrieval metadata batch hydration behavior."""

from pathlib import Path

import pytest

from homllm.common.types import Vector
from homllm.retrieval.bm25 import BM25Retriever
from homllm.retrieval.vector import VectorRetriever


class _FakeTantivy:
    def search(self, query: str, top_k: int):
        return [
            ("doc_b", 10.0),
            ("doc_a", 9.0),
            ("doc_missing", 8.0),
        ][:top_k]


class _FakeDuckDB:
    def __init__(self):
        self.calls = []

    def get_document_candidate_data_batch(self, doc_ids: list[str]):
        self.calls.append(list(doc_ids))
        return {
            "doc_a": {
                "file": "pkg/a.py",
                "symbol_id": "sym:a",
                "content": "def a(): return 1",
                "granularity_level": "fine",
                "span_start": 1,
                "span_end": 2,
                "parent_symbol_id": None,
                "entity_ids": ["sym:a"],
                "doc_type": "symbol",
            },
            "doc_b": {
                "file": "pkg/b.py",
                "symbol_id": "sym:b",
                "content": "def b(): return 2",
                "granularity_level": "fine",
                "span_start": 1,
                "span_end": 2,
                "parent_symbol_id": None,
                "entity_ids": ["sym:b"],
                "doc_type": "symbol",
            },
        }


class _FakeEmbedder:
    def embed_query(self, query: str) -> Vector:
        return Vector(values=(0.1, 0.2))


class _FakeLance:
    def __init__(self):
        self.modes = []

    def search(self, query_vector: Vector, top_k: int, calibration_mode: str = "legacy"):
        self.modes.append(calibration_mode)
        return [
            ("doc_x", 0.99, "x_body", {"file_path": "pkg/x.py", "symbol_id": "sym:x"}),
            ("doc_y", 0.77, "y_body", {"file_path": "pkg/y.py", "symbol_id": "sym:y"}),
            ("doc_z", 0.66, "z_body", {"file_path": "pkg/z.py"}),
        ][:top_k]


def test_bm25_batch_hydration_preserves_order_and_missing_defaults():
    retriever = BM25Retriever.__new__(BM25Retriever)
    retriever._tantivy = _FakeTantivy()
    retriever._duckdb = _FakeDuckDB()

    candidates = BM25Retriever.search(retriever, "find auth", 3)

    assert [c.doc_id for c in candidates] == ["doc_b", "doc_a", "doc_missing"]
    assert retriever._duckdb.calls == [["doc_b", "doc_a", "doc_missing"]]

    missing = candidates[2]
    assert missing.file == ""
    assert missing.symbol_id is None
    assert missing.content == ""
    assert missing.doc_type is None
    assert missing.entity_ids == ()


def test_vector_batch_hydration_preserves_order_and_metadata_fallback():
    retriever = VectorRetriever.__new__(VectorRetriever)
    retriever.embedder = _FakeEmbedder()
    retriever.calibration_mode = "legacy"
    retriever._lancedb = _FakeLance()
    retriever._duckdb = _FakeDuckDB()

    candidates = VectorRetriever.search(retriever, "find auth", 3)

    assert [c.doc_id for c in candidates] == ["doc_x", "doc_y", "doc_z"]
    assert retriever._duckdb.calls == [["doc_x", "doc_y", "doc_z"]]
    assert retriever._lancedb.modes == ["legacy"]

    # doc_x/doc_y fall back to Lance metadata because batch map does not include them
    assert candidates[0].file == "pkg/x.py"
    assert candidates[0].symbol_id == "sym:x"
    assert candidates[0].content == "x_body"

    assert candidates[1].file == "pkg/y.py"
    assert candidates[1].symbol_id == "sym:y"
    assert candidates[1].content == "y_body"

    # doc_z keeps content fallback and absent symbol_id when metadata missing.
    assert candidates[2].file == "pkg/z.py"
    assert candidates[2].symbol_id is None
    assert candidates[2].content == "z_body"


def test_vector_batch_hydration_forwards_calibrated_mode():
    retriever = VectorRetriever.__new__(VectorRetriever)
    retriever.embedder = _FakeEmbedder()
    retriever.calibration_mode = "calibrated_v1"
    retriever._lancedb = _FakeLance()
    retriever._duckdb = _FakeDuckDB()

    VectorRetriever.search(retriever, "find auth", 1)

    assert retriever._lancedb.modes == ["calibrated_v1"]


def test_vector_retriever_rejects_unknown_calibration_mode():
    with pytest.raises(ValueError, match="vector calibration_mode"):
        VectorRetriever(
            Path("indexes/vectors.lance"),
            _FakeEmbedder(),
            calibration_mode="invalid_mode",
        )
