"""DuckDB adapter for metadata and graph storage.

Extended for entity-centric indexing (Plan A) with:
- entities table: Extended entity metadata
- relations table: Typed relations between entities
- chunks table: Hierarchical chunks at multiple granularity levels
- index_schema_version: Backward-compatible versioning
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

import duckdb

from homllm.common.types import (
    CallEdge,
    ChunkInfo,
    EntityInfo,
    FileInfo,
    RelationInfo,
    SymbolInfo,
    SymbolKind,
)
from homllm.indexer.interfaces import StorageAdapter

logger = logging.getLogger(__name__)

# Schema version for backward compatibility
INDEX_SCHEMA_VERSION = "2.0"  # Upgraded from 1.0 for Plan A


class DuckDBAdapter:
    """
    DuckDB adapter for relational metadata storage.
    
    Extended for entity-centric indexing with:
    - entities table
    - relations table
    - chunks table
    - Schema versioning
    """

    def __init__(self, db_path: Path):
        """
        Initialize DuckDB connection.
        
        Schema:
        - files: file_id, path, language, content_hash, line_count, indexed_at
        - symbols: symbol_id, file_id, name, kind, start_line, end_line, signature
        - call_edges: caller_id, callee_id, call_site_line
        - entities: entity_id, entity_type, name, file_path, span_start, span_end, ...
        - relations: src_entity_id, dst_entity_id, relation_type, extraction_source
        - chunks: chunk_id, file_path, content, granularity_level, span_start, span_end
        - index_metadata: key, value
        """
        self.db_path = db_path
        self.conn: Optional[duckdb.DuckDBPyConnection] = None

    def connect(self) -> None:
        """Establish database connection."""
        if self.conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = duckdb.connect(str(self.db_path))
            self.initialize_schema()
            self._check_schema_version()

    def _check_schema_version(self) -> None:
        """
        Check schema version and log warning if mixed versions detected.
        
        Per user feedback: Add runtime check to log warning if loading
        mixed versions during transition.
        """
        stored_version = self.get_metadata("index_schema_version")
        if stored_version and stored_version != INDEX_SCHEMA_VERSION:
            logger.warning(
                f"Schema version mismatch: stored={stored_version}, "
                f"current={INDEX_SCHEMA_VERSION}. Some features may be unavailable."
            )
            if stored_version < INDEX_SCHEMA_VERSION:
                logger.info(
                    "Legacy index detected. Entity-centric features will be "
                    "unavailable until re-indexing."
                )

    def get_schema_version(self) -> str:
        """Get the stored schema version, defaulting to 1.0 for legacy indexes."""
        return self.get_metadata("index_schema_version") or "1.0"

    def is_legacy_index(self) -> bool:
        """Check if this is a legacy index (pre-Plan A)."""
        return self.get_schema_version() < INDEX_SCHEMA_VERSION

    def initialize_schema(self) -> None:
        """Create database schema if it doesn't exist."""
        if self.conn is None:
            return

        # Create files table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                file_id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                language TEXT,
                content_hash TEXT NOT NULL,
                line_count INTEGER,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create symbols table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS symbols (
                symbol_id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                start_line INTEGER,
                end_line INTEGER,
                signature TEXT,
                parent_id TEXT,
                content TEXT
            )
        """)

        # Create call_edges table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS call_edges (
                caller_id TEXT NOT NULL,
                callee_id TEXT NOT NULL,
                call_site_line INTEGER,
                PRIMARY KEY (caller_id, callee_id, call_site_line)
            )
        """)

        # Create index_metadata table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS index_metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Create index on symbol names for fast lookup
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name)
        """)

        # =========================================================================
        # Entity-Centric Indexing Tables (Plan A)
        # =========================================================================

        # Create entities table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                entity_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                span_start INTEGER NOT NULL,
                span_end INTEGER NOT NULL,
                docstring_hash TEXT,
                granularity_level TEXT DEFAULT 'fine',
                confidence_score REAL DEFAULT 0.0,
                has_type_annotation BOOLEAN DEFAULT FALSE,
                is_exported BOOLEAN DEFAULT FALSE,
                parent_entity_id TEXT,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create relations table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS relations (
                src_entity_id TEXT NOT NULL,
                dst_entity_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                extraction_source TEXT NOT NULL,
                PRIMARY KEY (src_entity_id, dst_entity_id, relation_type)
            )
        """)

        # Create chunks table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                content TEXT NOT NULL,
                granularity_level TEXT NOT NULL,
                span_start INTEGER NOT NULL,
                span_end INTEGER NOT NULL,
                entity_ids TEXT,
                symbol_name TEXT
            )
        """)

        # Create indexes for efficient lookups
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_entities_file ON entities(file_path)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_relations_src ON relations(src_entity_id)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_relations_dst ON relations(dst_entity_id)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_path)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_granularity ON chunks(granularity_level)
        """)

        # Migration: add symbol_name column for name_score linkage (if missing)
        try:
            self.conn.execute("ALTER TABLE chunks ADD COLUMN symbol_name TEXT")
        except Exception:
            pass  # Column already exists

    def insert_file(self, file_info: FileInfo) -> None:
        """Insert file metadata."""
        if self.conn is None:
            self.connect()

        normalized_path = str(file_info.path).replace("\\", "/")

        # Plain INSERT: full rebuilds call reset_index_data() and incremental
        # rebuilds call delete_file_data() first, so no primary-key conflicts
        # are possible. INSERT OR REPLACE on TEXT primary keys is pathologically
        # slow in DuckDB (super-linear, ~10x slower) and made full-repo indexing
        # unbounded on real repositories.
        self.conn.execute(
            """
            INSERT INTO files 
            (file_id, path, language, content_hash, line_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                file_info.file_id,
                normalized_path,
                file_info.language,
                file_info.content_hash,
                file_info.line_count,
            ],
        )

    def insert_symbol(self, symbol: SymbolInfo, file_id: str, content: Optional[str] = None) -> None:
        """Insert symbol metadata."""
        if self.conn is None:
            self.connect()

        # Plain INSERT: safe because reset_index_data()/delete_file_data()
        # clear rows first (see insert_file). Avoids the pathological
        # INSERT OR REPLACE behavior on TEXT primary keys.
        self.conn.execute(
            """
            INSERT INTO symbols
            (symbol_id, file_id, name, kind, start_line, end_line, signature, parent_id, content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                symbol.id,
                file_id,
                symbol.name,
                symbol.kind.value,
                symbol.start_line,
                symbol.end_line,
                symbol.signature,
                symbol.parent_id,
                content,
            ],
        )

    def get_symbol_content(self, symbol_id: str) -> Optional[str]:
        """Get symbol content by symbol_id."""
        if self.conn is None:
            self.connect()

        result = self.conn.execute(
            "SELECT content FROM symbols WHERE symbol_id = ?", [symbol_id]
        ).fetchone()
        return result[0] if result and result[0] else None

    def insert_call_edge(self, edge: CallEdge) -> None:
        """Insert call graph edge."""
        if self.conn is None:
            self.connect()

        # Plain INSERT: the graph builder dedupes edges before storage, so no
        # primary-key conflicts are possible. Avoids the slow INSERT OR IGNORE
        # path on composite TEXT keys at full-repo scale.
        self.conn.execute(
            """
            INSERT INTO call_edges
            (caller_id, callee_id, call_site_line)
            VALUES (?, ?, ?)
            """,
            [edge.caller_id, edge.callee_id, edge.call_site_line],
        )

    def get_doc_ids_for_file(self, file_path: str) -> list[str]:
        """Return document IDs currently indexed for a file."""
        if self.conn is None:
            self.connect()

        variants = self._path_variants(file_path)
        placeholders = ", ".join(["?"] * len(variants))
        chunk_rows = self.conn.execute(
            f"""
            SELECT chunk_id
            FROM chunks
            WHERE file_path IN ({placeholders})
            ORDER BY chunk_id
            """,
            variants,
        ).fetchall()
        if chunk_rows:
            return [row[0] for row in chunk_rows]

        file_ids = self._get_file_ids_for_path(file_path)
        if not file_ids:
            return []

        doc_ids: list[str] = []
        for file_id in file_ids:
            rows = self.conn.execute(
                """
                SELECT symbol_id
                FROM symbols
                WHERE file_id = ?
                ORDER BY symbol_id
                """,
                [file_id],
            ).fetchall()
            for row in rows:
                doc_ids.append(f"{file_id}:{row[0]}")

        return doc_ids

    @staticmethod
    def _resolve_symbol_id_from_doc_id(doc_id: str) -> str:
        """Resolve symbol ID using the legacy retrieval mapping contract."""
        return doc_id.split(":", 1)[1] if ":" in doc_id else doc_id

    def get_document_candidate_data_batch(
        self,
        doc_ids: list[str],
    ) -> dict[str, Optional[dict[str, Any]]]:
        """
        Resolve retrieval-facing metadata in batch for document IDs.

        This method deduplicates request IDs for efficient SQL lookup while
        preserving per-doc semantics of ``get_document_candidate_data``.
        """
        if self.conn is None:
            self.connect()
        if not doc_ids:
            return {}

        # Deduplicate requested IDs while preserving first-seen order.
        unique_doc_ids = list(dict.fromkeys(doc_ids))
        by_doc_id: dict[str, Optional[dict[str, Any]]] = {
            doc_id: None for doc_id in unique_doc_ids
        }

        placeholders = ", ".join(["?"] * len(unique_doc_ids))
        try:
            chunk_rows = self.conn.execute(
                f"""
                SELECT chunk_id, file_path, content, granularity_level, entity_ids, span_start, span_end, symbol_name
                FROM chunks
                WHERE chunk_id IN ({placeholders})
                """,
                unique_doc_ids,
            ).fetchall()
            has_symbol_name = True
        except Exception:
            chunk_rows = self.conn.execute(
                f"""
                SELECT chunk_id, file_path, content, granularity_level, entity_ids, span_start, span_end
                FROM chunks
                WHERE chunk_id IN ({placeholders})
                """,
                unique_doc_ids,
            ).fetchall()
            has_symbol_name = False

        chunk_payload: dict[str, dict[str, Any]] = {}
        first_entity_ids: list[str] = []
        for row in chunk_rows:
            chunk_id, file_path, content, granularity_level, entity_ids_raw, span_start, span_end = row[:7]
            symbol_name = row[7] if has_symbol_name and len(row) > 7 else None
            entity_ids = json.loads(entity_ids_raw) if entity_ids_raw else []
            symbol_id = entity_ids[0] if entity_ids else None
            if symbol_id:
                first_entity_ids.append(symbol_id)
            chunk_payload[str(chunk_id)] = {
                "doc_id": str(chunk_id),
                "file": file_path,
                "symbol_id": symbol_id,
                "content": content,
                "granularity_level": granularity_level,
                "entity_ids": entity_ids,
                "span_start": span_start,
                "span_end": span_end,
                "parent_symbol_id": None,
                "doc_type": "chunk",
                "symbol_name": symbol_name,
            }

        parent_by_symbol_id: dict[str, Any] = {}
        if first_entity_ids:
            unique_symbol_ids = list(dict.fromkeys(first_entity_ids))
            symbol_placeholders = ", ".join(["?"] * len(unique_symbol_ids))
            parent_rows = self.conn.execute(
                f"""
                SELECT symbol_id, parent_id
                FROM symbols
                WHERE symbol_id IN ({symbol_placeholders})
                """,
                unique_symbol_ids,
            ).fetchall()
            parent_by_symbol_id = {str(symbol_id): parent_id for symbol_id, parent_id in parent_rows}

        for chunk_id, payload in chunk_payload.items():
            symbol_id = payload.get("symbol_id")
            if symbol_id:
                payload["parent_symbol_id"] = parent_by_symbol_id.get(symbol_id)
            by_doc_id[chunk_id] = payload

        unresolved_doc_ids = [doc_id for doc_id in unique_doc_ids if by_doc_id[doc_id] is None]
        if not unresolved_doc_ids:
            return by_doc_id

        symbol_id_by_doc_id = {
            doc_id: self._resolve_symbol_id_from_doc_id(doc_id)
            for doc_id in unresolved_doc_ids
        }
        unique_resolved_symbol_ids = list(dict.fromkeys(symbol_id_by_doc_id.values()))
        if not unique_resolved_symbol_ids:
            return by_doc_id

        symbol_placeholders = ", ".join(["?"] * len(unique_resolved_symbol_ids))
        symbol_rows = self.conn.execute(
            f"""
            SELECT s.symbol_id, f.path, s.content, e.granularity_level, s.start_line, s.end_line, s.parent_id
            FROM symbols s
            LEFT JOIN files f ON f.file_id = s.file_id
            LEFT JOIN entities e ON e.entity_id = s.symbol_id
            WHERE s.symbol_id IN ({symbol_placeholders})
            """,
            unique_resolved_symbol_ids,
        ).fetchall()
        symbol_payload = {
            str(symbol_id): {
                "file": file_path or "",
                "symbol_id": str(symbol_id),
                "content": content or "",
                "granularity_level": granularity_level,
                "entity_ids": [str(symbol_id)],
                "span_start": span_start,
                "span_end": span_end,
                "parent_symbol_id": parent_symbol_id,
                "doc_type": "symbol",
            }
            for symbol_id, file_path, content, granularity_level, span_start, span_end, parent_symbol_id in symbol_rows
        }

        for doc_id, symbol_id in symbol_id_by_doc_id.items():
            payload = symbol_payload.get(symbol_id)
            if payload is None:
                continue
            by_doc_id[doc_id] = {
                "doc_id": doc_id,
                "file": payload["file"],
                "symbol_id": payload["symbol_id"],
                "content": payload["content"],
                "granularity_level": payload["granularity_level"],
                "entity_ids": payload["entity_ids"],
                "span_start": payload["span_start"],
                "span_end": payload["span_end"],
                "parent_symbol_id": payload["parent_symbol_id"],
                "doc_type": payload["doc_type"],
            }

        return by_doc_id

    def get_document_candidate_data(self, doc_id: str) -> Optional[dict[str, Any]]:
        """
        Resolve retrieval-facing metadata for a stored document.

        Supports both chunk-based IDs (preferred) and legacy symbol IDs.
        """
        return self.get_document_candidate_data_batch([doc_id]).get(doc_id)

    def delete_file_data(self, file_path: str) -> None:
        """Delete all index rows associated with a file path."""
        if self.conn is None:
            self.connect()

        file_ids = self._get_file_ids_for_path(file_path)
        if not file_ids:
            return

        symbol_ids: list[str] = []
        for file_id in file_ids:
            rows = self.conn.execute(
                "SELECT symbol_id FROM symbols WHERE file_id = ?",
                [file_id],
            ).fetchall()
            symbol_ids.extend(row[0] for row in rows)

        entity_paths = self._path_variants(file_path)
        entity_ids: list[str] = []
        for variant in entity_paths:
            rows = self.conn.execute(
                "SELECT entity_id FROM entities WHERE file_path = ?",
                [variant],
            ).fetchall()
            entity_ids.extend(row[0] for row in rows)

        for symbol_id in symbol_ids:
            self.conn.execute(
                "DELETE FROM call_edges WHERE caller_id = ? OR callee_id = ?",
                [symbol_id, symbol_id],
            )
            self.conn.execute(
                "DELETE FROM relations WHERE src_entity_id = ? OR dst_entity_id = ?",
                [symbol_id, symbol_id],
            )

        for entity_id in entity_ids:
            self.conn.execute(
                "DELETE FROM relations WHERE src_entity_id = ? OR dst_entity_id = ?",
                [entity_id, entity_id],
            )

        for file_id in file_ids:
            self.conn.execute("DELETE FROM symbols WHERE file_id = ?", [file_id])
            self.conn.execute("DELETE FROM files WHERE file_id = ?", [file_id])

        for variant in entity_paths:
            self.conn.execute("DELETE FROM chunks WHERE file_path = ?", [variant])
            self.conn.execute("DELETE FROM entities WHERE file_path = ?", [variant])

    def reset_index_data(self) -> None:
        """Clear all indexed rows while preserving schema."""
        if self.conn is None:
            self.connect()

        self.conn.execute("DELETE FROM call_edges")
        self.conn.execute("DELETE FROM relations")
        self.conn.execute("DELETE FROM chunks")
        self.conn.execute("DELETE FROM entities")
        self.conn.execute("DELETE FROM symbols")
        self.conn.execute("DELETE FROM files")

    def get_all_files(self) -> list[FileInfo]:
        """Return all indexed files."""
        if self.conn is None:
            self.connect()

        rows = self.conn.execute(
            """
            SELECT file_id, path, language, content_hash, line_count
            FROM files
            ORDER BY path
            """
        ).fetchall()

        return [
            FileInfo(
                file_id=row[0],
                path=Path(row[1]),
                language=row[2],
                content_hash=row[3],
                line_count=row[4],
                parse_error=False,
            )
            for row in rows
        ]

    def get_all_symbols(self) -> list[SymbolInfo]:
        """Return all indexed symbols with file paths."""
        if self.conn is None:
            self.connect()

        rows = self.conn.execute(
            """
            SELECT s.symbol_id, s.name, s.kind, f.path, s.start_line,
                   s.end_line, s.signature, s.parent_id
            FROM symbols s
            JOIN files f ON f.file_id = s.file_id
            ORDER BY f.path, s.start_line, s.name
            """
        ).fetchall()

        symbols: list[SymbolInfo] = []
        for row in rows:
            try:
                kind = SymbolKind(row[2])
            except ValueError:
                continue

            symbols.append(
                SymbolInfo(
                    id=row[0],
                    name=row[1],
                    kind=kind,
                    file=row[3],
                    start_line=row[4],
                    end_line=row[5],
                    signature=row[6],
                    parent_id=row[7],
                )
            )

        return symbols

    def get_all_call_edges(self) -> list[CallEdge]:
        """Return all call edges."""
        if self.conn is None:
            self.connect()

        rows = self.conn.execute(
            """
            SELECT caller_id, callee_id, call_site_line
            FROM call_edges
            ORDER BY caller_id, callee_id, call_site_line
            """
        ).fetchall()

        return [
            CallEdge(
                caller_id=row[0],
                callee_id=row[1],
                call_site_line=row[2],
            )
            for row in rows
        ]

    def get_all_entities(self) -> list[EntityInfo]:
        """Return all entities."""
        if self.conn is None:
            self.connect()

        rows = self.conn.execute(
            """
            SELECT entity_id, entity_type, name, file_path, span_start, span_end,
                   docstring_hash, granularity_level, confidence_score,
                   has_type_annotation, is_exported, parent_entity_id
            FROM entities
            ORDER BY file_path, span_start, name
            """
        ).fetchall()

        return [
            EntityInfo(
                entity_id=row[0],
                entity_type=row[1],
                name=row[2],
                file_path=row[3],
                span_start=row[4],
                span_end=row[5],
                docstring_hash=row[6],
                granularity_level=row[7],
                confidence_score=row[8],
                has_type_annotation=row[9],
                is_exported=row[10],
                parent_entity_id=row[11],
            )
            for row in rows
        ]

    def get_all_relations(self) -> list[RelationInfo]:
        """Return all relations."""
        if self.conn is None:
            self.connect()

        rows = self.conn.execute(
            """
            SELECT src_entity_id, dst_entity_id, relation_type, extraction_source
            FROM relations
            ORDER BY src_entity_id, dst_entity_id, relation_type
            """
        ).fetchall()

        return [
            RelationInfo(
                src_entity_id=row[0],
                dst_entity_id=row[1],
                relation_type=row[2],
                extraction_source=row[3],
            )
            for row in rows
        ]

    def get_all_chunks(self) -> list[ChunkInfo]:
        """Return all chunks."""
        if self.conn is None:
            self.connect()

        try:
            rows = self.conn.execute(
                """
                SELECT chunk_id, file_path, content, granularity_level,
                       span_start, span_end, entity_ids, symbol_name
                FROM chunks
                ORDER BY file_path, granularity_level, span_start
                """
            ).fetchall()
            rows_have_symbol_name = True
        except Exception:
            rows = self.conn.execute(
                """
                SELECT chunk_id, file_path, content, granularity_level,
                       span_start, span_end, entity_ids
                FROM chunks
                ORDER BY file_path, granularity_level, span_start
                """
            ).fetchall()
            rows_have_symbol_name = False

        chunks: list[ChunkInfo] = []
        for row in rows:
            entity_ids = tuple(json.loads(row[6])) if row[6] else ()
            symbol_name = row[7] if rows_have_symbol_name and len(row) > 7 else None
            chunks.append(
                ChunkInfo(
                    chunk_id=row[0],
                    file_path=row[1],
                    content=row[2],
                    granularity_level=row[3],
                    span_start=row[4],
                    span_end=row[5],
                    entity_ids=entity_ids,
                    symbol_name=symbol_name,
                )
            )
        return chunks

    # =========================================================================
    # Entity-Centric Indexing Methods (Plan A)
    # =========================================================================

    def insert_entity(self, entity: EntityInfo) -> None:
        """Insert entity metadata."""
        if self.conn is None:
            self.connect()
        normalized_file_path = self._normalize_path(entity.file_path)

        # Plain INSERT: safe because reset_index_data()/delete_file_data()
        # clear rows first (see insert_file). Avoids the pathological
        # INSERT OR REPLACE behavior on TEXT primary keys.
        self.conn.execute(
            """
            INSERT INTO entities
            (entity_id, entity_type, name, file_path, span_start, span_end,
             docstring_hash, granularity_level, confidence_score,
             has_type_annotation, is_exported, parent_entity_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                entity.entity_id,
                entity.entity_type,
                entity.name,
                normalized_file_path,
                entity.span_start,
                entity.span_end,
                entity.docstring_hash,
                entity.granularity_level,
                entity.confidence_score,
                entity.has_type_annotation,
                entity.is_exported,
                entity.parent_entity_id,
            ],
        )

    def insert_relation(self, relation: RelationInfo) -> None:
        """Insert typed relation."""
        if self.conn is None:
            self.connect()

        # Plain INSERT: the graph builder dedupes relations before storage, so
        # no primary-key conflicts are possible. Avoids the slow INSERT OR
        # IGNORE path on composite TEXT keys at full-repo scale.
        self.conn.execute(
            """
            INSERT INTO relations
            (src_entity_id, dst_entity_id, relation_type, extraction_source)
            VALUES (?, ?, ?, ?)
            """,
            [
                relation.src_entity_id,
                relation.dst_entity_id,
                relation.relation_type,
                relation.extraction_source,
            ],
        )

    def insert_chunk(self, chunk: ChunkInfo) -> None:
        """Insert hierarchical chunk."""
        if self.conn is None:
            self.connect()
        normalized_file_path = self._normalize_path(chunk.file_path)

        # Serialize entity_ids as JSON
        entity_ids_json = json.dumps(list(chunk.entity_ids))
        symbol_name = chunk.symbol_name or ""

        # Plain INSERT: safe because reset_index_data()/delete_file_data()
        # clear rows first (see insert_file). Avoids the pathological
        # INSERT OR REPLACE behavior on TEXT primary keys.
        self.conn.execute(
            """
            INSERT INTO chunks
            (chunk_id, file_path, content, granularity_level, span_start, span_end, entity_ids, symbol_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                chunk.chunk_id,
                normalized_file_path,
                chunk.content,
                chunk.granularity_level,
                chunk.span_start,
                chunk.span_end,
                entity_ids_json,
                symbol_name,
            ],
        )

    def get_entities_by_file(self, file_path: str) -> list[EntityInfo]:
        """Get all entities for a file."""
        if self.conn is None:
            self.connect()

        variants = self._path_variants(file_path)
        placeholders = ", ".join(["?"] * len(variants))
        result = self.conn.execute(
            f"""
            SELECT entity_id, entity_type, name, file_path, span_start, span_end,
                   docstring_hash, granularity_level, confidence_score,
                   has_type_annotation, is_exported, parent_entity_id
            FROM entities WHERE file_path IN ({placeholders})
            ORDER BY span_start
            """,
            variants,
        ).fetchall()

        return [
            EntityInfo(
                entity_id=row[0],
                entity_type=row[1],
                name=row[2],
                file_path=row[3],
                span_start=row[4],
                span_end=row[5],
                docstring_hash=row[6],
                granularity_level=row[7],
                confidence_score=row[8],
                has_type_annotation=row[9],
                is_exported=row[10],
                parent_entity_id=row[11],
            )
            for row in result
        ]

    def get_relations_by_entity(self, entity_id: str) -> list[RelationInfo]:
        """Get all relations for an entity (as source or destination)."""
        if self.conn is None:
            self.connect()

        result = self.conn.execute(
            """
            SELECT src_entity_id, dst_entity_id, relation_type, extraction_source
            FROM relations
            WHERE src_entity_id = ? OR dst_entity_id = ?
            ORDER BY relation_type
            """,
            [entity_id, entity_id],
        ).fetchall()

        return [
            RelationInfo(
                src_entity_id=row[0],
                dst_entity_id=row[1],
                relation_type=row[2],
                extraction_source=row[3],
            )
            for row in result
        ]

    def get_chunks_by_granularity(self, granularity: str) -> list[ChunkInfo]:
        """Get all chunks at a specific granularity level."""
        if self.conn is None:
            self.connect()

        try:
            result = self.conn.execute(
                """
                SELECT chunk_id, file_path, content, granularity_level,
                       span_start, span_end, entity_ids, symbol_name
                FROM chunks WHERE granularity_level = ?
                ORDER BY file_path, span_start
                """,
                [granularity],
            ).fetchall()
            rows_have_symbol_name = True
        except Exception:
            result = self.conn.execute(
                """
                SELECT chunk_id, file_path, content, granularity_level,
                       span_start, span_end, entity_ids
                FROM chunks WHERE granularity_level = ?
                ORDER BY file_path, span_start
                """,
                [granularity],
            ).fetchall()
            rows_have_symbol_name = False

        chunks = []
        for row in result:
            entity_ids = tuple(json.loads(row[6])) if row[6] else ()
            symbol_name = row[7] if rows_have_symbol_name and len(row) > 7 else None
            chunks.append(
                ChunkInfo(
                    chunk_id=row[0],
                    file_path=row[1],
                    content=row[2],
                    granularity_level=row[3],
                    span_start=row[4],
                    span_end=row[5],
                    entity_ids=entity_ids,
                    symbol_name=symbol_name,
                )
            )
        return chunks

    def get_entity_count(self) -> int:
        """Get total count of entities in the index."""
        if self.conn is None:
            self.connect()

        result = self.conn.execute("SELECT COUNT(*) FROM entities").fetchone()
        return result[0] if result else 0

    def get_relation_count(self) -> int:
        """Get total count of relations in the index."""
        if self.conn is None:
            self.connect()

        result = self.conn.execute("SELECT COUNT(*) FROM relations").fetchone()
        return result[0] if result else 0

    def get_chunk_count(self) -> int:
        """Get total count of chunks in the index."""
        if self.conn is None:
            self.connect()

        result = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
        return result[0] if result else 0
    
    def get_chunk_granularity(self, doc_id: str) -> Optional[str]:
        """
        Get granularity level for a chunk or symbol.
        
        Plan B: Used for intent-driven granularity boosting.
        
        Args:
            doc_id: Document ID (chunk_id or symbol_id)
        
        Returns:
            Granularity level ('fine', 'medium', 'coarse') or None
        """
        if self.conn is None:
            self.connect()
        
        # Try chunks table first
        try:
            result = self.conn.execute(
                "SELECT granularity_level FROM chunks WHERE chunk_id = ?",
                [doc_id],
            ).fetchone()
            if result:
                return result[0]
        except Exception:
            pass
        
        # Try entities table
        try:
            result = self.conn.execute(
                "SELECT granularity_level FROM entities WHERE entity_id = ?",
                [doc_id],
            ).fetchone()
            if result:
                return result[0]
        except Exception:
            pass
        
        return None

    # =========================================================================
    # Metadata Methods
    # =========================================================================

    def set_metadata(self, key: str, value: str) -> None:
        """Set index metadata."""
        if self.conn is None:
            self.connect()

        self.conn.execute(
            """
            INSERT OR REPLACE INTO index_metadata (key, value)
            VALUES (?, ?)
            """,
            [key, value],
        )

    def get_metadata(self, key: str) -> Optional[str]:
        """Get index metadata."""
        if self.conn is None:
            self.connect()

        result = self.conn.execute(
            "SELECT value FROM index_metadata WHERE key = ?", [key]
        ).fetchone()
        return result[0] if result else None

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def _path_variants(self, file_path: str) -> list[str]:
        normalized = self._normalize_path(file_path)
        slash = normalized.replace("\\", "/")
        backslash = slash.replace("/", "\\")
        return sorted({normalized, slash, backslash})

    def _normalize_path(self, file_path: str) -> str:
        return str(file_path).lstrip("./").replace("\\", "/")

    def _get_file_ids_for_path(self, file_path: str) -> list[str]:
        variants = self._path_variants(file_path)
        placeholders = ", ".join(["?"] * len(variants))
        rows = self.conn.execute(
            f"SELECT file_id FROM files WHERE path IN ({placeholders})",
            variants,
        ).fetchall()
        return sorted({row[0] for row in rows})

