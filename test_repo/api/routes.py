"""
API route definitions.
These routes use decorators from security.decorators which creates
a multi-hop dependency that RAG systems must trace.
"""

from typing import Dict, Any, List, Optional
from api.dependencies import get_database, get_search_engine, get_current_user
from security.decorators import require_auth, require_admin, audit_log
from core.exceptions import InvalidTokenError, PermissionDeniedError, SearchError

@require_auth
@audit_log("search")
def search_endpoint(query: str, token: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search endpoint for authenticated users.
    Uses @require_auth decorator which validates JWT token.
    
    Args:
        query: Search query string
        token: JWT authentication token (injected by decorator)
        user: User information (injected by @require_auth decorator)
        
    Returns:
        Search results dictionary
    """
    try:
        # Get search engine components
        search_components = get_search_engine()
        indexer = search_components['indexer']
        ranking = search_components['ranking']
        permission_filter = search_components['filter']
        
        # Generate query embedding
        query_embedding = indexer.generate_embedding(query)
        if query_embedding is None:
            return {"error": "Failed to generate query embedding", "results": []}
        
        # Mock candidate results (in production, would query database)
        candidate_embeddings = [
            ("file1.py", "function", query_embedding * 0.9),
            ("file2.py", "class", query_embedding * 0.8),
        ]
        
        # Rank results
        ranked_results = ranking.rank_results(query_embedding, candidate_embeddings)
        
        # Filter by permissions
        filtered_results = permission_filter.filter_by_permissions(ranked_results, user)
        
        return {
            "query": query,
            "results": filtered_results,
            "count": len(filtered_results)
        }
    except Exception as e:
        raise SearchError(f"Search failed: {e}")

@require_auth
@require_admin
@audit_log("admin_search")
def admin_search_endpoint(query: str, token: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Admin-only search endpoint.
    Uses both @require_auth and @require_admin decorators.
    This creates a decorator chain that RAG systems must trace.
    
    Args:
        query: Search query string
        token: JWT authentication token
        user: User information (must be admin)
        
    Returns:
        Search results dictionary (unfiltered for admins)
    """
    try:
        search_components = get_search_engine()
        indexer = search_components['indexer']
        ranking = search_components['ranking']
        
        # Generate query embedding
        query_embedding = indexer.generate_embedding(query)
        if query_embedding is None:
            return {"error": "Failed to generate query embedding", "results": []}
        
        # Mock candidate results
        candidate_embeddings = [
            ("file1.py", "function", query_embedding * 0.9),
            ("file2.py", "class", query_embedding * 0.8),
        ]
        
        # Rank results (admins see all results, no filtering)
        ranked_results = ranking.rank_results(query_embedding, candidate_embeddings)
        
        return {
            "query": query,
            "results": ranked_results,
            "count": len(ranked_results),
            "admin": True
        }
    except Exception as e:
        raise SearchError(f"Admin search failed: {e}")

@require_auth
def index_endpoint(file_path: str, token: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Index a file endpoint.
    Requires authentication but not admin (any user can index their own files).
    
    Args:
        file_path: Path to file to index
        token: JWT authentication token
        user: User information
        
    Returns:
        Indexing result dictionary
    """
    try:
        search_components = get_search_engine()
        indexer = search_components['indexer']
        
        success = indexer.index_file(file_path)
        
        return {
            "file_path": file_path,
            "indexed": success,
            "user": user.get('username')
        }
    except Exception as e:
        return {
            "file_path": file_path,
            "indexed": False,
            "error": str(e)
        }
