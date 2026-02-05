"""Protocols and interfaces for Indexer layer."""

from pathlib import Path
from typing import Iterator, Optional, Protocol

from homllm.common.config import IndexerConfig
from homllm.common.types import Document, FileInfo, SymbolInfo, Vector


class ScanConfig:
    """Configuration for file scanning."""

    def __init__(self, config: IndexerConfig):
        self.languages = config.languages
        self.ignore_patterns = config.ignore_patterns


class ParseResult:
    """Result of parsing a single file."""

    def __init__(
        self,
        symbols: list[SymbolInfo],
        content: str,
        parse_error: bool = False,
        error_message: Optional[str] = None,
        tree: Optional[object] = None,  # Tree-Sitter Tree object for entity extraction
    ):
        self.symbols = symbols
        self.content = content
        self.parse_error = parse_error
        self.error_message = error_message
        self.tree = tree  # Plan A: Used by entity extractor


class FileScanner(Protocol):
    """Protocol for file scanning."""

    def scan(self, repo_path: Path, config: ScanConfig) -> Iterator[FileInfo]:
        """
        Yields file metadata without loading content.
        
        Properties:
        - Respects .gitignore by default
        - Language filters are config-driven
        - Returns deterministic ordering (sorted by path)
        """
        ...


class CodeParser(Protocol):
    """Protocol for code parsing."""

    def parse(self, file_path: Path, language: str) -> ParseResult:
        """
        Returns AST and extracted symbols.
        
        Failure Handling:
        - Parse errors are logged, not raised
        - Unparseable files return ParseResult with parse_error=True
        - Parser crashes are isolated per-file
        """
        ...

    def supported_languages(self) -> list[str]:
        """Returns list of parseable languages."""
        ...


class LexicalIndex(Protocol):
    """Protocol for BM25/lexical indexing."""

    def index(self, documents: Iterator[Document]) -> None:
        """
        Indexes documents. Idempotent for same input.
        
        Properties:
        - Deterministic for same input
        - No side effects beyond index updates
        """
        ...

    def search(self, query: str, top_k: int) -> list[tuple[str, float]]:
        """
        Returns ranked results as (doc_id, score) tuples.
        
        Properties:
        - Deterministic for same query
        - Results sorted by score descending
        """
        ...


class Embedder(Protocol):
    """Protocol for embedding generation."""

    def embed_code(self, code: str) -> Vector:
        """
        Embeds code chunk. NO instruction prefix.
        
        Properties:
        - Deterministic (same input → same vector)
        - Offline-only (no API calls)
        - Raw embedding (no instruction wrapping)
        """
        ...

    def embed_query(self, query: str) -> Vector:
        """
        Embeds query WITH instruction prefix (asymmetric).
        
        Properties:
        - Deterministic
        - Instruction-aware for query side
        """
        ...

    @property
    def dimension(self) -> int:
        """Returns embedding dimension. MUST be consistent."""
        ...


class StorageAdapter(Protocol):
    """Protocol for storage operations."""

    def read(self, key: str) -> bytes:
        """Read data by key."""
        ...

    def write(self, key: str, data: bytes) -> None:
        """Write data by key."""
        ...

    def exists(self, key: str) -> bool:
        """Check if key exists."""
        ...

    def delete(self, key: str) -> None:
        """Delete data by key."""
        ...
