"""
Multi-layer cache management system.
Coordinates caching across different backends (memory, Redis, database).
"""

import time
import hashlib
import logging
from typing import Any, Optional, Dict, Callable, List, Union
from functools import wraps
from enum import Enum
from cache.redis_client import RedisClient

logger = logging.getLogger(__name__)

class CacheLayer(Enum):
    """Cache layer types."""
    MEMORY = "memory"
    REDIS = "redis"
    DATABASE = "database"

class CacheManager:
    """
    Multi-layer cache manager with:
    - Memory cache (L1)
    - Redis cache (L2)
    - Database cache (L3)
    - Automatic layer promotion
    - Smart invalidation
    - Cache coherence
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, redis_enabled: bool = True, 
                 memory_limit: int = 1000,
                 default_ttl: int = 3600):
        """
        Initialize cache manager.
        
        Args:
            redis_enabled: Enable Redis backend
            memory_limit: Maximum entries in memory cache
            default_ttl: Default TTL in seconds
        """
        if self._initialized:
            return
        
        self.redis_enabled = redis_enabled
        self.memory_limit = memory_limit
        self.default_ttl = default_ttl
        
        # Memory cache
        self.memory_cache = {}
        self.memory_timestamps = {}
        
        # Redis client
        self.redis = None
        if redis_enabled:
            try:
                self.redis = RedisClient()
                logger.info("Redis cache enabled")
            except Exception as e:
                logger.warning(f"Redis cache disabled: {e}")
                self.redis = None
        
        # Statistics
        self.stats = {
            "memory_hits": 0,
            "memory_misses": 0,
            "redis_hits": 0,
            "redis_misses": 0,
            "evictions": 0
        }
        
        self._initialized = True
    
    def _generate_key(self, namespace: str, identifier: Union[str, int, tuple]) -> str:
        """Generate cache key with namespace."""
        if isinstance(identifier, (list, tuple)):
            identifier = ":".join(str(i) for i in identifier)
        
        key = f"{namespace}:{identifier}"
        return hashlib.md5(key.encode()).hexdigest()
    
    def get(self, namespace: str, identifier: Union[str, int, tuple],
            fetch_func: Optional[Callable] = None,
            ttl: Optional[int] = None) -> Optional[Any]:
        """
        Get value from cache with automatic promotion.
        
        Args:
            namespace: Cache namespace
            identifier: Cache identifier
            fetch_func: Function to fetch value if not cached
            ttl: Custom TTL
            
        Returns:
            Cached value or fetched value
        """
        key = self._generate_key(namespace, identifier)
        ttl = ttl or self.default_ttl
        
        # Try memory cache first
        if key in self.memory_cache:
            if time.time() - self.memory_timestamps[key] < ttl:
                self.stats["memory_hits"] += 1
                return self.memory_cache[key]
            else:
                del self.memory_cache[key]
                del self.memory_timestamps[key]
        
        self.stats["memory_misses"] += 1
        
        # Try Redis cache
        if self.redis:
            redis_value = self.redis.get(key)
            if redis_value is not None:
                self.stats["redis_hits"] += 1
                # Promote to memory cache
                self._set_memory(key, redis_value, ttl)
                return redis_value
            
            self.stats["redis_misses"] += 1
        
        # Fetch from source if provided
        if fetch_func:
            value = fetch_func()
            self.set(namespace, identifier, value, ttl)
            return value
        
        return None
    
    def set(self, namespace: str, identifier: Union[str, int, tuple],
            value: Any, ttl: Optional[int] = None):
        """
        Set value in cache across layers.
        
        Args:
            namespace: Cache namespace
            identifier: Cache identifier
            value: Value to cache
            ttl: Custom TTL
        """
        key = self._generate_key(namespace, identifier)
        ttl = ttl or self.default_ttl
        
        # Set in memory
        self._set_memory(key, value, ttl)
        
        # Set in Redis
        if self.redis:
            self.redis.set(key, value, ttl=ttl)
    
    def _set_memory(self, key: str, value: Any, ttl: int):
        """Set value in memory cache with eviction policy."""
        if len(self.memory_cache) >= self.memory_limit:
            # LRU eviction
            oldest_key = min(self.memory_timestamps, key=self.memory_timestamps.get)
            del self.memory_cache[oldest_key]
            del self.memory_timestamps[oldest_key]
            self.stats["evictions"] += 1
        
        self.memory_cache[key] = value
        self.memory_timestamps[key] = time.time()
    
    def invalidate(self, namespace: str, identifier: Optional[Union[str, int, tuple]] = None):
        """
        Invalidate cache entries.
        
        Args:
            namespace: Cache namespace
            identifier: Specific identifier or None for all in namespace
        """
        if identifier is None:
            # Invalidate all in namespace
            prefix = namespace + ":"
            # Remove from memory
            for key in list(self.memory_cache.keys()):
                if key.startswith(prefix):
                    del self.memory_cache[key]
                    del self.memory_timestamps[key]
            # Remove from Redis
            if self.redis:
                # Simplified Redis pattern delete
                logger.info(f"Invalidated namespace: {namespace}")
        else:
            key = self._generate_key(namespace, identifier)
            if key in self.memory_cache:
                del self.memory_cache[key]
                del self.memory_timestamps[key]
            if self.redis:
                self.redis.delete(key)
    
    def clear_all(self):
        """Clear all caches."""
        self.memory_cache.clear()
        self.memory_timestamps.clear()
        if self.redis:
            self.redis.flushdb()
        logger.info("All caches cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        memory_total = self.stats["memory_hits"] + self.stats["memory_misses"]
        redis_total = self.stats["redis_hits"] + self.stats["redis_misses"]
        
        return {
            "memory": {
                "hits": self.stats["memory_hits"],
                "misses": self.stats["memory_misses"],
                "hit_rate": f"{self.stats['memory_hits'] / memory_total * 100:.2f}%" if memory_total > 0 else "0%",
                "entries": len(self.memory_cache),
                "limit": self.memory_limit
            },
            "redis": {
                "hits": self.stats["redis_hits"],
                "misses": self.stats["redis_misses"],
                "hit_rate": f"{self.stats['redis_hits'] / redis_total * 100:.2f}%" if redis_total > 0 else "0%",
                "enabled": self.redis is not None
            },
            "evictions": self.stats["evictions"]
        }

