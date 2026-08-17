"""Unit tests for TantivyAdapter BM25 commit reliability.

Real tantivy-backed indexing observed a transient failure mode on large
repositories: the writer commit writes segment files but never registers them,
leaving an unsearchable index (meta.json with zero segments) while the
pipeline continues. These tests cover the adapter's commit verification and
single-retry behavior.
"""

import json
from pathlib import Path

import pytest

try:
    import tantivy  # noqa: F401
except ImportError:
    tantivy = None

from homllm.common.types import Document
from homllm.indexer.storage.tantivy_adapter import TantivyAdapter

pytestmark = pytest.mark.skipif(
    tantivy is None,
    reason="tantivy not installed",
)


def _docs(count: int = 5) -> list[Document]:
    return [
        Document(
            doc_id=f"doc-{i:04d}",
            content=f"symbol_{i} cosh acos Abs complexes body {i}",
            metadata={"file_path": f"mod{i % 2}.py"},
        )
        for i in range(count)
    ]


def _registered_segments(index_path: Path) -> int:
    meta = json.loads((index_path / "meta.json").read_text(encoding="utf-8"))
    return len(meta.get("segments", []))


def test_tantivy_adapter_indexes_documents_and_registers_commit(tmp_path: Path) -> None:
    adapter = TantivyAdapter(tmp_path / "bm25.index")
    adapter.index(iter(_docs(20)))

    assert _registered_segments(adapter.index_path) >= 1
    results = adapter.search("cosh", 10)
    assert len(results) >= 1
    assert adapter._registered_doc_count() == 20


def test_tantivy_adapter_retries_commit_on_transient_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient commit exception must be retried with a fresh writer and end
    with a searchable index instead of a swallowed, half-committed state."""
    real_commit = tantivy.IndexWriter.commit
    state = {"calls": 0}

    def flaky_commit(self):
        state["calls"] += 1
        if state["calls"] == 1:
            raise OSError("simulated transient commit failure")
        return real_commit(self)

    monkeypatch.setattr(tantivy.IndexWriter, "commit", flaky_commit)

    adapter = TantivyAdapter(tmp_path / "bm25.index")
    adapter.index(iter(_docs(10)))

    assert state["calls"] == 2
    assert adapter._registered_doc_count() == 10
    assert len(adapter.search("cosh", 5)) >= 1


def test_tantivy_adapter_retries_when_commit_silently_fails_to_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate the production failure: commit returns without registering the
    documents (segment files written, meta.json never updated). The adapter
    must detect the missing registration, reset, and retry."""
    real_count = TantivyAdapter._registered_doc_count
    captured: dict[str, int | bool] = {}
    reset_calls: list[int] = []
    real_reset = TantivyAdapter.reset

    def flaky_count(self) -> int:
        if "base" not in captured:
            captured["base"] = real_count(self)
            return int(captured["base"])
        if captured.get("skipped_once") is None:
            captured["skipped_once"] = True
            # Pretend the commit never registered the new documents.
            return int(captured["base"])
        return real_count(self)

    def spying_reset(self) -> None:
        reset_calls.append(1)
        real_reset(self)

    monkeypatch.setattr(TantivyAdapter, "_registered_doc_count", flaky_count)
    monkeypatch.setattr(TantivyAdapter, "reset", spying_reset)

    adapter = TantivyAdapter(tmp_path / "bm25.index")
    adapter.index(iter(_docs(10)))

    assert reset_calls == [1]
    assert adapter._registered_doc_count() == 10
    assert len(adapter.search("cosh", 5)) >= 1


def test_tantivy_adapter_raises_when_commit_persistently_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def always_fail_commit(self):
        raise OSError("persistent commit failure")

    monkeypatch.setattr(tantivy.IndexWriter, "commit", always_fail_commit)

    adapter = TantivyAdapter(tmp_path / "bm25.index")
    with pytest.raises(RuntimeError, match="BM25 index commit failed after retry"):
        adapter.index(iter(_docs(5)))


def test_tantivy_adapter_reset_then_index_rebuilds_cleanly(tmp_path: Path) -> None:
    adapter = TantivyAdapter(tmp_path / "bm25.index")
    adapter.index(iter(_docs(10)))
    assert adapter._registered_doc_count() == 10

    adapter.reset()
    assert adapter._registered_doc_count() == 0

    adapter.index(iter(_docs(25)))
    assert adapter._registered_doc_count() == 25
    assert len(adapter.search("Abs", 10)) >= 1
