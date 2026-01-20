"""
Dependency injection for API routes.
This module provides dependencies that routes depend on.
"""

from typing import Dict, Any, Optional
from database.connection import ConnectionPool
from database.adapters.postgres import PostgresAdapter
from search_engine.indexer import DocumentIndexer
from search_engine.ranking import RankingEngine
from search_engine.filters import PermissionFilter
from security.auth_manager import AuthManager

# Global instances (in production, would use proper DI container)
_connection_pool: Optional[ConnectionPool] = None
_indexer: Optional[DocumentIndexer] = None
_ranking_engine: Optional[RankingEngine] = None
_permission_filter: Optional[PermissionFilter] = None
_auth_manager: Optional[AuthManager] = None

def get_connection_pool() -> ConnectionPool:
    """Get or create connection pool singleton."""
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = ConnectionPool()
    return _connection_pool

def get_database(adapter_type: str = "postgres") -> PostgresAdapter:
    """
    Get a database adapter from the connection pool.
    This is dependency injection - routes depend on this function.
    
    Args:
        adapter_type: Type of adapter ("postgres" or "sqlite")
        
    Returns:
        Database adapter instance
    """
    pool = get_connection_pool()
    return pool.acquire(adapter_type)

def get_search_engine() -> Dict[str, Any]:
    """
    Get search engine components.
    Returns a dictionary with indexer, ranking engine, and filter.
    
    Returns:
        Dictionary with 'indexer', 'ranking', and 'filter' keys
    """
    global _indexer, _ranking_engine, _permission_filter
    
    if _indexer is None:
        _indexer = DocumentIndexer()
    
    if _ranking_engine is None:
        _ranking_engine = RankingEngine()
    
    if _permission_filter is None:
        _permission_filter = PermissionFilter()
    
    return {
        'indexer': _indexer,
        'ranking': _ranking_engine,
        'filter': _permission_filter
    }

def get_current_user(token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get current user from authentication token.
    This is used by dependency injection in routes.
    
    Args:
        token: Optional JWT token
        
    Returns:
        User information dictionary or None
    """
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    
    if not token:
        return None
    
    try:
        return _auth_manager.get_user_from_token(token)
    except Exception:
        return None
