"""
Distributed caching layer with Redis support.
Provides high-performance caching for search results, embeddings, and metadata.
"""

from cache.redis_client import RedisClient
from cache.cache_manager import CacheManager
from cache.decorators import cache_result, invalidate_cache

__all__ = [
    "RedisClient",
    "CacheManager",
    "cache_result",
    "invalidate_cache"
]
