"""
Cache decorators for easy cache management.
"""

from functools import wraps
from typing import Callable, Optional
from cache.cache_manager import CacheManager

cache_manager = CacheManager()

def cache_result(namespace: str, ttl: Optional[int] = None):
    """
    Decorator to cache function results.
    
    Args:
        namespace: Cache namespace
        ttl: Custom TTL
        
    Usage:
        @cache_result("search_results", ttl=3600)
        def search_documents(query: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            cache_key = (func.__name__, args, tuple(sorted(kwargs.items())))
            
            # Try to get from cache
            result = cache_manager.get(namespace, cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache_manager.set(namespace, cache_key, result, ttl)
            return result
        
        return wrapper
    return decorator

def invalidate_cache(namespace: str, identifier_func: Optional[Callable] = None):
    """
    Decorator to invalidate cache after function execution.
    
    Args:
        namespace: Cache namespace to invalidate
        identifier_func: Optional function to generate cache identifier
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            
            if identifier_func:
                identifier = identifier_func(*args, **kwargs)
                cache_manager.invalidate(namespace, identifier)
            else:
                cache_manager.invalidate(namespace)
            
            return result
        
        return wrapper
    return decorator

