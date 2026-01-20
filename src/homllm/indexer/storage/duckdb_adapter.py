"""DuckDB adapter for metadata and graph storage."""

import json
from pathlib import Path
from typing import Any, Optional

import duckdb

from homllm.common.types import CallEdge, FileInfo, SymbolInfo
from homllm.indexer.interfaces import StorageAdapter


class DuckDBAdapter:
    """DuckDB adapter for relational metadata storage."""

    def __init__(self, db_path: Path):
        """
        Initialize DuckDB connection.
        
        Schema:
        - files: file_id, path, language, content_hash, line_count, indexed_at
        - symbols: symbol_id, file_id, name, kind, start_line, end_line, signature
        - call_edges: caller_id, callee_id, call_site_line
        - index_metadata: key, value
        """
        self.db_path = db_path
        self.conn: Optional[duckdb.DuckDBPyConnection] = None
        # TODO: Initialize connection and create schema

    def connect(self) -> None:
        """Establish database connection."""
        if self.conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = duckdb.connect(str(self.db_path))
            self.initialize_schema()

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
