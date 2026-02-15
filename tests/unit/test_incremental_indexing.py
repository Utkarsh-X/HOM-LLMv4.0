"""Unit tests for incremental indexing primitives."""

from pathlib import Path
from uuid import uuid4

from homllm.common.types import CallEdge, ChunkInfo, EntityInfo, FileInfo, RelationInfo, SymbolInfo, SymbolKind
from homllm.indexer.incremental_indexer import IncrementalIndexer
from homllm.indexer.storage.duckdb_adapter import DuckDBAdapter


def _workspace_tmp_dir() -> Path:
    path = Path("artifacts") / "test_tmp" / "incremental_indexing"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _file(file_id: str, path: str, content_hash: str) -> FileInfo:
    return FileInfo(
        file_id=file_id,
        path=Path(path),
        language="python",
        content_hash=content_hash,
        line_count=1,
        parse_error=False,
    )


def test_incremental_indexer_detects_new_changed_and_deleted_files():
    tmp_dir = _workspace_tmp_dir()
    cache_path = tmp_dir / f"{uuid4().hex}_cache.json"

    first_scan = [
        _file("f1", "pkg/a.py", "hash_a_v1"),
        _file("f2", "pkg/b.py", "hash_b_v1"),
    ]
    first_indexer = IncrementalIndexer(cache_path)
    first_diff = first_indexer.diff(first_scan)
    assert sorted(first_diff.changed_paths) == ["pkg/a.py", "pkg/b.py"]
    assert first_diff.deleted_paths == []
    first_indexer.save(first_scan)

    second_scan = [
        _file("f1", "pkg/a.py", "hash_a_v2"),
        _file("f3", "pkg/c.py", "hash_c_v1"),
    ]
    second_indexer = IncrementalIndexer(cache_path)
    second_diff = second_indexer.diff(second_scan)

    assert sorted(second_diff.changed_paths) == ["pkg/a.py", "pkg/c.py"]
    assert second_diff.deleted_paths == ["pkg/b.py"]
    assert second_diff.new_paths == ["pkg/c.py"]

    second_indexer.save(second_scan)
    third_indexer = IncrementalIndexer(cache_path)
    third_diff = third_indexer.diff(second_scan)
    assert third_diff.changed_paths == []
    assert third_diff.deleted_paths == []
    assert sorted(str(file_info.path).replace("\\", "/") for file_info in third_diff.unchanged_files) == [
        "pkg/a.py",
        "pkg/c.py",
    ]


def test_duckdb_file_cleanup_removes_related_rows():
    tmp_dir = _workspace_tmp_dir()
    db_path = tmp_dir / f"{uuid4().hex}_test.duckdb"
    adapter = DuckDBAdapter(db_path)
    adapter.connect()
    adapter.reset_index_data()

    file_info = _file("f1", "pkg/mod.py", "hash_mod")
    adapter.insert_file(file_info)

    symbol_one = SymbolInfo(
        id="sym:one",
        name="one",
        kind=SymbolKind.FUNCTION,
        file="pkg/mod.py",
        start_line=1,
        end_line=2,
    )
    symbol_two = SymbolInfo(
        id="sym:two",
        name="two",
        kind=SymbolKind.FUNCTION,
        file="pkg/mod.py",
        start_line=3,
        end_line=4,
    )
    adapter.insert_symbol(symbol_one, file_info.file_id, "def one():\n    pass")
    adapter.insert_symbol(symbol_two, file_info.file_id, "def two():\n    pass")
    adapter.insert_call_edge(CallEdge(caller_id=symbol_one.id, callee_id=symbol_two.id, call_site_line=2))

    entity = EntityInfo(
        entity_id="ent:mod",
        entity_type="import",
        name="one",
        file_path="pkg/mod.py",
        span_start=1,
        span_end=1,
    )
    adapter.insert_entity(entity)
    adapter.insert_relation(
        RelationInfo(
            src_entity_id=entity.entity_id,
            dst_entity_id=symbol_one.id,
            relation_type="defines",
            extraction_source="test",
        )
    )
    adapter.insert_chunk(
        ChunkInfo(
            chunk_id="chunk:mod",
            file_path="pkg/mod.py",
            content="def one(): pass",
            granularity_level="fine",
            span_start=1,
            span_end=2,
            entity_ids=(entity.entity_id,),
        )
    )

    assert adapter.get_doc_ids_for_file("pkg\\mod.py") == ["chunk:mod"]

    adapter.delete_file_data("pkg/mod.py")

    assert adapter.get_doc_ids_for_file("pkg/mod.py") == []
    assert adapter.get_all_files() == []
    assert adapter.get_all_symbols() == []
    assert adapter.get_all_call_edges() == []
    assert adapter.get_all_entities() == []
    assert adapter.get_all_relations() == []
    assert adapter.get_all_chunks() == []


def test_get_document_candidate_data_prefers_chunk_then_symbol():
    tmp_dir = _workspace_tmp_dir()
    db_path = tmp_dir / f"{uuid4().hex}_candidate_data.duckdb"
    adapter = DuckDBAdapter(db_path)
    adapter.connect()
    adapter.reset_index_data()

    file_info = _file("f9", "pkg/data.py", "hash_data")
    adapter.insert_file(file_info)

    symbol = SymbolInfo(
        id="sym:data",
        name="data",
        kind=SymbolKind.FUNCTION,
        file="pkg/data.py",
        start_line=1,
        end_line=2,
    )
    adapter.insert_symbol(symbol, file_info.file_id, "def data():\n    return 1")
    adapter.insert_chunk(
        ChunkInfo(
            chunk_id="chunk:data",
            file_path="pkg/data.py",
            content="def data():\n    return 1",
            granularity_level="fine",
            span_start=1,
            span_end=2,
            entity_ids=("sym:data",),
        )
    )

    chunk_data = adapter.get_document_candidate_data("chunk:data")
    assert chunk_data is not None
    assert chunk_data["doc_type"] == "chunk"
    assert chunk_data["symbol_id"] == "sym:data"

    symbol_data = adapter.get_document_candidate_data("f9:sym:data")
    assert symbol_data is not None
    assert symbol_data["doc_type"] == "symbol"
    assert symbol_data["symbol_id"] == "sym:data"


def test_get_document_candidate_data_batch_parity_and_dedup():
    tmp_dir = _workspace_tmp_dir()
    db_path = tmp_dir / f"{uuid4().hex}_candidate_data_batch.duckdb"
    adapter = DuckDBAdapter(db_path)
    adapter.connect()
    adapter.reset_index_data()

    file_info = _file("f10", "pkg/batch.py", "hash_batch")
    adapter.insert_file(file_info)

    parent = SymbolInfo(
        id="sym:parent",
        name="parent",
        kind=SymbolKind.FUNCTION,
        file="pkg/batch.py",
        start_line=1,
        end_line=2,
    )
    child = SymbolInfo(
        id="sym:child",
        name="child",
        kind=SymbolKind.FUNCTION,
        file="pkg/batch.py",
        start_line=3,
        end_line=6,
        parent_id="sym:parent",
    )
    adapter.insert_symbol(parent, file_info.file_id, "def parent():\n    pass")
    adapter.insert_symbol(child, file_info.file_id, "def child():\n    return 1")
    adapter.insert_chunk(
        ChunkInfo(
            chunk_id="chunk:batch",
            file_path="pkg/batch.py",
            content="def child():\n    return 1",
            granularity_level="fine",
            span_start=3,
            span_end=6,
            entity_ids=("sym:child",),
        )
    )

    requested = [
        "chunk:batch",
        "f10:sym:child",
        "missing:doc",
        "chunk:batch",  # duplicate request should be deduped internally
    ]
    batch = adapter.get_document_candidate_data_batch(requested)

    assert set(batch.keys()) == {"chunk:batch", "f10:sym:child", "missing:doc"}
    assert batch["missing:doc"] is None
    assert batch["chunk:batch"] == adapter.get_document_candidate_data("chunk:batch")
    assert batch["f10:sym:child"] == adapter.get_document_candidate_data("f10:sym:child")
