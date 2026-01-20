"""
Abstract base classes (interfaces) for the search system.
These define contracts that implementations must follow.

WARNING: RAG systems often retrieve these empty interface definitions
instead of the actual implementations in adapters/ and services/.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Dict, Any
import numpy as np

class ISearchEngine(ABC):
    """Abstract interface for search engine implementations."""
    
    @abstractmethod
    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, str, float]]:
        """
        Perform semantic search for a query.
        
        Args:
            query: Search query string
            top_k: Number of results to return
            
        Returns:
            List of (file_path, entity_type, score) tuples
        """
        pass
    
    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the search backend."""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close connection to the search backend."""
        pass

class IDatabaseAdapter(ABC):
    """Abstract interface for database adapters."""
    
    @abstractmethod
    def connect(self) -> None:
        """Establish database connection."""
        pass
    
    @abstractmethod
    def query(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a SQL query.
        
        Args:
            sql: SQL query string
            params: Optional query parameters
            
        Returns:
            List of result dictionaries
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close database connection."""
        pass
    
    @abstractmethod
    def get_timeout(self) -> int:
        """Get the connection timeout value."""
        pass

class IIndexer(ABC):
    """Abstract interface for document indexers."""
    
    @abstractmethod
    def index_file(self, file_path: str) -> bool:
        """
        Index a single file.
        
        Args:
            file_path: Path to file to index
            
        Returns:
            True if indexing succeeded, False otherwise
        """
        pass
    
    @abstractmethod
    def index_directory(self, directory_path: str) -> int:
        """
        Index all files in a directory.
        
        Args:
            directory_path: Path to directory
            
        Returns:
            Number of files indexed
        """
        pass
    
    @abstractmethod
    def generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        Generate embedding vector for text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector or None if generation fails
        """
        pass
