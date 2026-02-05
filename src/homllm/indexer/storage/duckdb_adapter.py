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

from homllm.common.types import CallEdge, ChunkInfo, EntityInfo, FileInfo, RelationInfo, SymbolInfo
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
                entity_ids TEXT
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

    def insert_file(self, file_info: FileInfo) -> None:
        """Insert file metadata."""
        if self.conn is None:
            self.connect()

        self.conn.execute(
            """
            INSERT OR REPLACE INTO files 
            (file_id, path, language, content_hash, line_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                file_info.file_id,
                str(file_info.path),
                file_info.language,
                file_info.content_hash,
                file_info.line_count,
            ],
        )

    def insert_symbol(self, symbol: SymbolInfo, file_id: str, content: Optional[str] = None) -> None:
        """Insert symbol metadata."""
        if self.conn is None:
            self.connect()

        self.conn.execute(
            """
            INSERT OR REPLACE INTO symbols
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

        self.conn.execute(
            """
            INSERT OR IGNORE INTO call_edges
            (caller_id, callee_id, call_site_line)
            VALUES (?, ?, ?)
            """,
            [edge.caller_id, edge.callee_id, edge.call_site_line],
        )

    # =========================================================================
    # Entity-Centric Indexing Methods (Plan A)
    # =========================================================================

    def insert_entity(self, entity: EntityInfo) -> None:
        """Insert entity metadata."""
        if self.conn is None:
            self.connect()

        self.conn.execute(
            """
            INSERT OR REPLACE INTO entities
            (entity_id, entity_type, name, file_path, span_start, span_end,
             docstring_hash, granularity_level, confidence_score,
             has_type_annotation, is_exported, parent_entity_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                entity.entity_id,
                entity.entity_type,
                entity.name,
                entity.file_path,
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

        self.conn.execute(
            """
            INSERT OR IGNORE INTO relations
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

        # Serialize entity_ids as JSON
        entity_ids_json = json.dumps(list(chunk.entity_ids))

        self.conn.execute(
            """
            INSERT OR REPLACE INTO chunks
            (chunk_id, file_path, content, granularity_level, span_start, span_end, entity_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                chunk.chunk_id,
                chunk.file_path,
                chunk.content,
                chunk.granularity_level,
                chunk.span_start,
                chunk.span_end,
                entity_ids_json,
            ],
        )

    def get_entities_by_file(self, file_path: str) -> list[EntityInfo]:
        """Get all entities for a file."""
        if self.conn is None:
            self.connect()

        result = self.conn.execute(
            """
            SELECT entity_id, entity_type, name, file_path, span_start, span_end,
                   docstring_hash, granularity_level, confidence_score,
                   has_type_annotation, is_exported, parent_entity_id
            FROM entities WHERE file_path = ?
            ORDER BY span_start
            """,
            [file_path],
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

        result = self.conn.execute(
            """
            SELECT chunk_id, file_path, content, granularity_level,
                   span_start, span_end, entity_ids
            FROM chunks WHERE granularity_level = ?
            ORDER BY file_path, span_start
            """,
            [granularity],
        ).fetchall()

        return [
            ChunkInfo(
                chunk_id=row[0],
                file_path=row[1],
                content=row[2],
                granularity_level=row[3],
                span_start=row[4],
                span_end=row[5],
                entity_ids=tuple(json.loads(row[6])) if row[6] else (),
            )
            for row in result
        ]

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

