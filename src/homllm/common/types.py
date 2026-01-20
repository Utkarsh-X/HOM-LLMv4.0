"""Core types shared across all layers."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class Intent(str, Enum):
    """Query intent classification."""

    EXPLAIN = "explain"
    IMPLEMENT = "implement"
    REFACTOR = "refactor"
    DEBUG = "debug"
    SEARCH = "search"
    UNKNOWN = "unknown"


class SymbolKind(str, Enum):
    """Symbol type classification."""

    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    MODULE = "module"
    DECORATOR = "decorator"


@dataclass(frozen=True)
class FileInfo:
    """File metadata."""

    file_id: str
    path: Path
    language: Optional[str]
    content_hash: str
    line_count: int
    parse_error: bool = False


@dataclass(frozen=True)
class SymbolInfo:
    """Symbol metadata from AST parsing."""

    id: str
    name: str
    kind: SymbolKind
    file: str  # Relative path
    start_line: int
    end_line: int
    signature: Optional[str] = None
    decorators: tuple[str, ...] = ()
    parent_id: Optional[str] = None


@dataclass(frozen=True)
class CallEdge:
    """Call graph edge."""

    caller_id: str
    callee_id: str
    call_site_line: int


@dataclass(frozen=True)
class Document:
    """Document for indexing (BM25 or vector)."""

    doc_id: str
    content: str
    metadata: dict[str, str]  # file, symbol_id, etc.


@dataclass(frozen=True)
class Vector:
    """Embedding vector."""

    values: tuple[float, ...]

    @property
    def dimension(self) -> int:
        """Return vector dimension."""
        return len(self.values)
