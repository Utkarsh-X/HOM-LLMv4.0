"""
Custom exception hierarchy for the search system.
These exceptions are raised throughout the application and must be
imported from this module to maintain consistency.
"""

class SearchError(Exception):
    """Base exception for search-related errors."""
    pass

class DatabaseError(Exception):
    """Base exception for database-related errors."""
    pass

class ConnectionError(DatabaseError):
    """Raised when database connection fails or times out."""
    pass

class PoolExhaustedError(DatabaseError):
    """Raised when connection pool is exhausted."""
    def __init__(self, max_connections: int):
        self.max_connections = max_connections
        super().__init__(f"Connection pool exhausted. Max connections: {max_connections}")

class AuthenticationError(Exception):
    """Base exception for authentication-related errors."""
    pass

class InvalidTokenError(AuthenticationError):
    """Raised when JWT token is invalid, expired, or malformed."""
    def __init__(self, message: str = "Invalid or expired JWT token"):
        self.message = message
        super().__init__(message)

class PermissionDeniedError(AuthenticationError):
    """Raised when user lacks required permissions."""
    def __init__(self, required_permission: str):
        self.required_permission = required_permission
        super().__init__(f"Permission denied. Required: {required_permission}")

class IndexingError(Exception):
    """Raised when document indexing fails."""
    pass

class EmbeddingGenerationError(IndexingError):
    """Raised when embedding generation fails."""
    pass

class BinaryFileError(IndexingError):
    """Raised when attempting to index a binary file."""
    pass
