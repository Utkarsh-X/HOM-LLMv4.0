"""
Connection pool management for database adapters.
Implements singleton pattern for connection pooling.
"""

import threading
import time
from typing import Optional
from config import settings
from core.exceptions import PoolExhaustedError, ConnectionError

class ConnectionPool:
    """
    Singleton connection pool manager.
    Thread-safe connection pool that manages database connections.
    """
    
    _instance: Optional['ConnectionPool'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern implementation."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the connection pool."""
        if self._initialized:
            return
        
        self.max_connections = settings.DB_MAX_CONNECTIONS
        self.timeout = settings.DB_TIMEOUT
        self.pool_recycle = settings.DB_POOL_RECYCLE
        self._connections = []
        self._in_use = set()
        self._lock = threading.Lock()
        self._created_at = time.time()
        self._initialized = True
    
    def acquire(self, adapter_type: str = "postgres"):
        """
        Acquire a connection from the pool.
        
        Args:
            adapter_type: Type of adapter ("postgres" or "sqlite")
            
        Returns:
            Database adapter instance
            
        Raises:
            PoolExhaustedError: If pool is exhausted
            ConnectionError: If connection creation fails
        """
        with self._lock:
            # Check if pool is exhausted
            if len(self._in_use) >= self.max_connections:
                raise PoolExhaustedError(self.max_connections)
            
            # Recycle old connections
            current_time = time.time()
            if current_time - self._created_at > self.pool_recycle:
                self._connections = []
                self._created_at = current_time
            
            # Try to reuse existing connection
            if self._connections:
                conn = self._connections.pop()
            else:
                # Create new connection
                try:
                    if adapter_type == "postgres":
                        from database.adapters.postgres import PostgresAdapter
                        conn = PostgresAdapter()
                    else:
                        from database.adapters.sqlite_legacy import SQLiteLegacyAdapter
                        conn = SQLiteLegacyAdapter()
                    conn.connect()
                except Exception as e:
                    raise ConnectionError(f"Failed to create connection: {e}")
            
            self._in_use.add(id(conn))
            return conn
    
    def release(self, conn):
        """
        Release a connection back to the pool.
        
        Args:
            conn: Connection to release
        """
        with self._lock:
            conn_id = id(conn)
            if conn_id in self._in_use:
                self._in_use.remove(conn_id)
                # Only reuse if pool not full
                if len(self._connections) < self.max_connections:
                    self._connections.append(conn)
                else:
                    conn.close()
    
    def get_pool_stats(self) -> dict:
        """Get connection pool statistics."""
        with self._lock:
            return {
                "max_connections": self.max_connections,
                "active": len(self._in_use),
                "available": len(self._connections),
                "total_used": len(self._in_use) + len(self._connections)
            }
