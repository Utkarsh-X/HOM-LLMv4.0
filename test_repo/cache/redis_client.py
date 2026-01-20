"""
Redis client with connection pooling and distributed cache support.
Provides high-performance caching for the search system.
"""

import redis
import json
import pickle
import time
import logging
from typing import Any, Optional, Dict, List, Union, Callable
from datetime import timedelta
from functools import wraps
from config import settings

logger = logging.getLogger(__name__)

class RedisClient:
    """
    Redis client with advanced features:
    - Connection pooling
    - Automatic serialization/deserialization
    - Distributed cache invalidation
    - Cache statistics tracking
    - TTL management
    - Lua scripting support
    """
    
    _instance = None
    _lock = None
    
    def __new__(cls):
        if cls._instance is None:
            import threading
            if cls._lock is None:
                cls._lock = threading.Lock()
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, 
                 password: Optional[str] = None, max_connections: int = 50):
        """
        Initialize Redis client.
        
        Args:
            host: Redis server host
            port: Redis server port
            db: Database number
            password: Redis password
            max_connections: Maximum pool connections
        """
        if self._initialized:
            return
        
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.max_connections = max_connections
        
        # Connection pool
        self.pool = redis.ConnectionPool(
            host=host,
            port=port,
            db=db,
            password=password,
            max_connections=max_connections,
            decode_responses=True
        )
        
        self.client = redis.Redis(connection_pool=self.pool)
        
        # Statistics
        self._hits = 0
        self._misses = 0
        self._operations = {}
        self._initialized = True
        
        logger.info(f"Redis client initialized: {host}:{port}/{db}")
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None, 
            serializer: str = "json") -> bool:
        """
        Set a key-value pair with optional TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            serializer: Serialization method ("json" or "pickle")
            
        Returns:
            True if successful
        """
        try:
            if serializer == "pickle":
                serialized_value = pickle.dumps(value)
                self.client.set(f"pkl:{key}", serialized_value, ex=ttl)
            else:
                serialized_value = json.dumps(value, default=str)
                self.client.set(key, serialized_value, ex=ttl)
            
            self._track_operation("set", key)
            return True
        except Exception as e:
            logger.error(f"Failed to set cache key {key}: {e}")
            return False
    
    def get(self, key: str, deserializer: str = "json") -> Optional[Any]:
        """
        Get a cached value.
        
        Args:
            key: Cache key
            deserializer: Deserialization method
            
        Returns:
            Cached value or None
        """
        try:
            # Try JSON first
            value = self.client.get(key)
            if value is None:
                # Try pickle
                pkl_key = f"pkl:{key}"
                pkl_value = self.client.get(pkl_key)
                if pkl_value:
                    value = pickle.loads(pkl_value)
                    self._misses += 1
                    return value
                
                self._misses += 1
                return None
            
            self._hits += 1
            if deserializer == "json":
                return json.loads(value)
            return value
        except Exception as e:
            logger.error(f"Failed to get cache key {key}: {e}")
            self._misses += 1
            return None
    
    def delete(self, key: str) -> bool:
        """Delete a cache key."""
        try:
            self.client.delete(key)
            self.client.delete(f"pkl:{key}")
            self._track_operation("delete", key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete cache key {key}: {e}")
            return False
    
    def mget(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple keys at once."""
        try:
            values = self.client.mget(keys)
            result = {}
            for key, value in zip(keys, values):
                if value:
                    try:
                        result[key] = json.loads(value)
                    except:
                        result[key] = value
            
            self._hits += len(result)
            self._misses += len(keys) - len(result)
            return result
        except Exception as e:
            logger.error(f"Failed to mget: {e}")
            return {}
    
    def mset(self, mapping: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set multiple key-value pairs."""
        try:
            serialized = {k: json.dumps(v, default=str) for k, v in mapping.items()}
            self.client.mset(serialized)
            
            if ttl:
                for key in mapping.keys():
                    self.client.expire(key, ttl)
            
            return True
        except Exception as e:
            logger.error(f"Failed to mset: {e}")
            return False
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a numeric value."""
        try:
            return self.client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Failed to increment {key}: {e}")
            return None
    
    def exists(self, key: str) -> bool:
        """Check if key exists."""
        return self.client.exists(key) > 0
    
    def ttl(self, key: str) -> int:
        """Get TTL for a key (-1 if no expiry, -2 if doesn't exist)."""
        return self.client.ttl(key)
    
    def expire(self, key: str, ttl: int) -> bool:
        """Set expiration for a key."""
        return self.client.expire(key, ttl)
    
    def lpush(self, key: str, values: List[Any]) -> int:
        """Push values to a list."""
        try:
            serialized = [json.dumps(v, default=str) for v in values]
            return self.client.lpush(key, *serialized)
        except Exception as e:
            logger.error(f"Failed to lpush to {key}: {e}")
            return 0
    
    def lpop(self, key: str, count: int = 1) -> List[Any]:
        """Pop values from a list."""
        try:
            values = self.client.lpop(key, count)
            if not values:
                return []
            return [json.loads(v) if isinstance(v, str) else v for v in values]
        except Exception as e:
            logger.error(f"Failed to lpop from {key}: {e}")
            return []
    
    def zadd(self, key: str, mapping: Dict[str, float]) -> int:
        """Add members to sorted set."""
        return self.client.zadd(key, mapping)
    
    def zrange(self, key: str, start: int = 0, end: int = -1, 
               with_scores: bool = False) -> List[Any]:
        """Get range from sorted set."""
        return self.client.zrange(key, start, end, withscores=with_scores)
    
    def flushdb(self) -> bool:
        """Flush current database."""
        try:
            self.client.flushdb()
            return True
        except Exception as e:
            logger.error(f"Failed to flushdb: {e}")
            return False
    
    def info(self) -> Dict[str, Any]:
        """Get Redis info."""
        try:
            return self.client.info()
        except Exception as e:
            logger.error(f"Failed to get Redis info: {e}")
            return {}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        
        return {
            "hits": self._hits,
            "misses": self._misses,
            "total": total,
            "hit_rate": f"{hit_rate:.2f}%",
            "operations": self._operations
        }
    
    def _track_operation(self, op_type: str, key: str):
        """Track operation for statistics."""
        if op_type not in self._operations:
            self._operations[op_type] = 0
        self._operations[op_type] += 1
    
    def close(self):
        """Close Redis connection."""
        try:
            self.pool.disconnect()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")

