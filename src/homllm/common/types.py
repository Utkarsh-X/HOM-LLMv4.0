"""Core types shared across all layers."""

from dataclasses import dataclass, field
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
    # Entity-centric indexing additions (Plan A)
    IMPORT = "import"
    ALIAS = "alias"
    CONFIG_CONSTANT = "config_constant"
    TYPE_ALIAS = "type_alias"  # Optional, flag-gated


class RelationType(str, Enum):
    """Relation type classification for entity-centric indexing."""

    # Required relation types
    CALLS = "calls"
    DEFINES = "defines"
    USES = "uses"
    IMPORTS = "imports"
    INHERITS = "inherits"
    # Optional relation types (low cost, high ROI)
    OVERRIDES = "overrides"
    TYPE_ANNOTATES = "type_annotates"


class GranularityLevel(str, Enum):
    """Chunk granularity level for hierarchical chunking."""

    FINE = "fine"       # Symbol-level (functions, methods)
    MEDIUM = "medium"   # File sections / logical blocks
    COARSE = "coarse"   # File-level summary


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


# =============================================================================
# Entity-Centric Indexing Types (Plan A)
# =============================================================================


@dataclass(frozen=True)
class EntityInfo:
    """
    Entity metadata for entity-centric indexing.
    
    Each entity represents a distinct code element with:
    - Stable identifier (entity_id)
    - Type classification (entity_type)
    - Source location (file_path, span_start, span_end)
    - Confidence scoring for downstream ranking
    """

    entity_id: str                          # Stable hash
    entity_type: str                        # From SymbolKind
    name: str
    file_path: str
    span_start: int                         # Start line (1-indexed)
    span_end: int                           # End line (1-indexed)
    docstring_hash: Optional[str] = None    # Hash of docstring if present
    granularity_level: str = "fine"         # From GranularityLevel
    confidence_score: float = 0.0           # Config-driven score
    has_type_annotation: bool = False       # For confidence scoring
    is_exported: bool = False               # In __all__ or re-exported
    parent_entity_id: Optional[str] = None  # For nested entities


@dataclass(frozen=True)
class RelationInfo:
    """
    Typed relation between entities for graph-based retrieval.
    
    Relations are sparse and directional (src -> dst).
    """

    src_entity_id: str
    dst_entity_id: str
    relation_type: str                      # From RelationType
    extraction_source: str                  # e.g., "call_expression", "import_statement"


@dataclass(frozen=True)
class ChunkInfo:
    """
    Hierarchical chunk for multi-granularity indexing.
    
    Chunks are tagged with granularity level:
    - fine: Symbol-level (functions, methods)
    - medium: File sections / logical blocks
    - coarse: File-level summary (docstrings + signatures)
    """

    chunk_id: str
    file_path: str
    content: str
    granularity_level: str                  # From GranularityLevel
    span_start: int                         # Start line (1-indexed)
    span_end: int                           # End line (1-indexed)
    entity_ids: tuple[str, ...] = ()        # Linked entity IDs

