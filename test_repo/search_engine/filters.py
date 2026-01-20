"""
Permission-based filtering for search results.
Filters results based on user permissions and access control.
"""

from typing import List, Tuple, Dict, Any, Optional

class PermissionFilter:
    """
    Filters search results based on user permissions.
    Ensures users only see results they have access to.
    """
    
    def __init__(self):
        """Initialize the permission filter."""
        self._permission_cache = {}
    
    def filter_by_permissions(self, results: List[Tuple[str, str, float]],
                             user: Dict[str, Any]) -> List[Tuple[str, str, float]]:
        """
        Filter search results by user permissions.
        
        Args:
            results: List of (file_path, entity_type, score) tuples
            user: User information dictionary with permissions
            
        Returns:
            Filtered results that user has access to
        """
        if not user:
            return []
        
        # Admin users see everything
        if user.get('is_admin', False):
            return results
        
        # Regular users see only public or their own files
        user_id = user.get('user_id')
        filtered = []
        
        for file_path, entity_type, score in results:
            if self._has_access(file_path, user_id, user):
                filtered.append((file_path, entity_type, score))
        
        return filtered
    
    def _has_access(self, file_path: str, user_id: Optional[str], 
                    user: Dict[str, Any]) -> bool:
        """
        Check if user has access to a file.
        
        Args:
            file_path: Path to file
            user_id: User ID
            user: User information
            
        Returns:
            True if user has access, False otherwise
        """
        # Check cache
        cache_key = (file_path, user_id)
        if cache_key in self._permission_cache:
            return self._permission_cache[cache_key]
        
        # Simple access control: users can access files in their own directory
        # In production, this would query a permissions database
        has_access = False
        
        if user_id:
            # Users can access files in their user directory
            if f"/{user_id}/" in file_path or f"\\{user_id}\\" in file_path:
                has_access = True
            # Public files are accessible to all
            elif "/public/" in file_path or "\\public\\" in file_path:
                has_access = True
        
        # Cache result
        self._permission_cache[cache_key] = has_access
        return has_access
    
    def clear_cache(self):
        """Clear the permission cache."""
        self._permission_cache.clear()
