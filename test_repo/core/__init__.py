"""
Core module containing abstract interfaces and exception definitions.
"""

from core.interfaces import ISearchEngine, IDatabaseAdapter, IIndexer
from core.exceptions import (
    SearchError,
    DatabaseError,
    ConnectionError,
    PoolExhaustedError,
    AuthenticationError,
    InvalidTokenError,
    PermissionDeniedError,
    IndexingError,
    EmbeddingGenerationError,
    BinaryFileError
)

__all__ = [
    "ISearchEngine",
    "IDatabaseAdapter", 
    "IIndexer",
    "SearchError",
    "DatabaseError",
    "ConnectionError",
    "PoolExhaustedError",
    "AuthenticationError",
    "InvalidTokenError",
    "PermissionDeniedError",
    "IndexingError",
    "EmbeddingGenerationError",
    "BinaryFileError"
]
