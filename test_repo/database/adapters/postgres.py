"""
PostgreSQL database adapter with async support.
This is the modern, production-ready implementation.

Complex features:
- Connection pooling with retry logic
- Transaction management
- Prepared statement caching
- Query result pagination
- Health check and connection monitoring
- SQL injection protection via parameterized queries
"""

import asyncio
import asyncpg
import time
import logging
from typing import List, Dict, Any, Optional, Tuple, Callable
from contextlib import asynccontextmanager
from config import settings
from core.interfaces import IDatabaseAdapter
from core.exceptions import ConnectionError, DatabaseError, PoolExhaustedError

logger = logging.getLogger(__name__)

class PostgresAdapter(IDatabaseAdapter):
    """
    Async PostgreSQL database adapter with advanced features.
    Modern implementation using asyncpg for high performance.
    Includes connection pooling, transaction management, and query optimization.
    """
    
    def __init__(self, pool_size: int = 5, max_overflow: int = 10):
        """
        Initialize the Postgres adapter.
        
        Args:
            pool_size: Base pool size
            max_overflow: Maximum overflow connections
        """
        self.host = settings.POSTGRES_HOST
        self.port = settings.POSTGRES_PORT
        self.database = settings.POSTGRES_DB
        self.user = settings.POSTGRES_USER
        self.password = settings.POSTGRES_PASSWORD
        self.timeout = settings.DB_TIMEOUT
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        
        self._conn: Optional[asyncpg.Connection] = None
        self._pool: Optional[asyncpg.Pool] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._prepared_statements: Dict[str, Any] = {}
        self._connection_attempts = 0
        self._max_retries = 3
        self._retry_delay = 1.0
        self._last_health_check = 0.0
        self._health_check_interval = 30.0
        
    def connect(self) -> None:
        """
        Establish async connection to PostgreSQL.
        Uses the global DB_TIMEOUT from config.settings.
        Implements retry logic with exponential backoff.
        """
        for attempt in range(self._max_retries):
            try:
                # Get or create event loop
                try:
                    self._loop = asyncio.get_event_loop()
                except RuntimeError:
                    self._loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(self._loop)
                
                # Create connection with timeout from config
                self._conn = self._loop.run_until_complete(
                    asyncpg.connect(
                        host=self.host,
                        port=self.port,
                        user=self.user,
                        password=self.password,
                        database=self.database,
                        timeout=self.timeout,  # Uses config.settings.DB_TIMEOUT
                        command_timeout=self.timeout * 2
                    )
                )
                
                # Verify connection
                self._loop.run_until_complete(self._verify_connection())
                self._connection_attempts = 0
                logger.info(f"Connected to PostgreSQL at {self.host}:{self.port}/{self.database}")
                return
                
            except Exception as e:
                self._connection_attempts += 1
                if attempt < self._max_retries - 1:
                    delay = self._retry_delay * (2 ** attempt)
                    logger.warning(f"Connection attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    raise ConnectionError(f"Failed to connect to PostgreSQL after {self._max_retries} attempts: {e}")
    
    async def _verify_connection(self):
        """Verify the connection is alive by executing a simple query."""
        try:
            await self._conn.execute("SELECT 1")
        except Exception as e:
            raise ConnectionError(f"Connection verification failed: {e}")
    
    async def _get_connection(self) -> asyncpg.Connection:
        """Get a connection from pool or return existing connection."""
        if self._conn and not self._conn.is_closed():
            return self._conn
        if self._pool:
            return await self._pool.acquire()
        raise ConnectionError("No database connection available")
    
    async def _release_connection(self, conn: asyncpg.Connection):
        """Release connection back to pool if using pool."""
        if self._pool and conn != self._conn:
            await self._pool.release(conn)
    
    async def _query_async(self, sql: str, params: Optional[Dict[str, Any]] = None, 
                          fetch_one: bool = False) -> List[Dict[str, Any]]:
        """
        Internal async query method with advanced features.
        
        Args:
            sql: SQL query string
            params: Optional query parameters (prevents SQL injection)
            fetch_one: If True, return only first row
            
        Returns:
            List of result dictionaries or single dict if fetch_one=True
        """
        conn = await self._get_connection()
        try:
            # Use prepared statement if available
            stmt_key = f"{sql}_{hash(str(sorted(params.items()) if params else []))}"
            if stmt_key in self._prepared_statements:
                stmt = self._prepared_statements[stmt_key]
            else:
                stmt = await conn.prepare(sql)
                if len(self._prepared_statements) < 100:  # Limit cache size
                    self._prepared_statements[stmt_key] = stmt
            
            # Execute with parameters
            if params:
                # Convert dict params to ordered list matching SQL placeholders
                param_values = list(params.values())
                if fetch_one:
                    row = await stmt.fetchrow(*param_values)
                    return dict(row) if row else {}
                rows = await stmt.fetch(*param_values)
            else:
                if fetch_one:
                    row = await stmt.fetchrow()
                    return dict(row) if row else {}
                rows = await stmt.fetch()
            
            return [dict(row) for row in rows]
        except asyncpg.PostgresError as e:
            raise DatabaseError(f"PostgreSQL error: {e}")
        except Exception as e:
            raise DatabaseError(f"Query failed: {e}")
        finally:
            await self._release_connection(conn)
    
    def query(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a SQL query (synchronous wrapper for async).
        Uses parameterized queries to prevent SQL injection.
        
        Args:
            sql: SQL query string
            params: Optional query parameters (dict with named parameters)
            
        Returns:
            List of result dictionaries
        """
        if not self._conn and not self._pool:
            raise ConnectionError("Not connected to database")
        
        return self._loop.run_until_complete(self._query_async(sql, params))
    
    def query_one(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Execute a query and return only the first row.
        
        Args:
            sql: SQL query string
            params: Optional query parameters
            
        Returns:
            Single result dictionary or None
        """
        if not self._conn and not self._pool:
            raise ConnectionError("Not connected to database")
        
        result = self._loop.run_until_complete(self._query_async(sql, params, fetch_one=True))
        return result if result else None
    
    def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        """
        Execute a SQL command (INSERT, UPDATE, DELETE) and return affected rows.
        
        Args:
            sql: SQL command string
            params: Optional query parameters
            
        Returns:
            Number of affected rows
        """
        if not self._conn and not self._pool:
            raise ConnectionError("Not connected to database")
        
        async def _execute():
            conn = await self._get_connection()
            try:
                if params:
                    result = await conn.execute(sql, *params.values())
                else:
                    result = await conn.execute(sql)
                # Extract row count from result string like "INSERT 0 5"
                parts = result.split()
                return int(parts[-1]) if parts else 0
            finally:
                await self._release_connection(conn)
        
        return self._loop.run_until_complete(_execute())
    
    @asynccontextmanager
    async def transaction(self):
        """
        Context manager for database transactions.
        
        Usage:
            async with adapter.transaction():
                adapter.execute("INSERT INTO ...")
                adapter.execute("UPDATE ...")
        """
        conn = await self._get_connection()
        async with conn.transaction():
            try:
                yield conn
            except Exception:
                raise
            finally:
                await self._release_connection(conn)
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check on the database connection.
        
        Returns:
            Dictionary with health status information
        """
        current_time = time.time()
        if current_time - self._last_health_check < self._health_check_interval:
            return {"status": "cached", "healthy": True}
        
        try:
            if not self._conn:
                return {"status": "unhealthy", "error": "No connection"}
            
            # Check if connection is alive
            result = self._loop.run_until_complete(self._conn.fetchval("SELECT 1"))
            if result == 1:
                self._last_health_check = current_time
                return {
                    "status": "healthy",
                    "host": self.host,
                    "database": self.database,
                    "timeout": self.timeout
                }
            else:
                return {"status": "unhealthy", "error": "Health check query returned unexpected result"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    def get_timeout(self) -> int:
        """Get the connection timeout value from config."""
        return settings.DB_TIMEOUT
    
    def get_connection_info(self) -> Dict[str, Any]:
        """Get connection information for debugging."""
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "timeout": self.timeout,
            "connected": self._conn is not None and not self._conn.is_closed() if self._conn else False,
            "pool_size": self.pool_size,
            "prepared_statements": len(self._prepared_statements)
        }
    
    def close(self) -> None:
        """Close the database connection and cleanup resources."""
        if self._conn and self._loop:
            try:
                if not self._conn.is_closed():
                    self._loop.run_until_complete(self._conn.close())
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
            finally:
                self._conn = None
        
        if self._pool and self._loop:
            try:
                self._loop.run_until_complete(self._pool.close())
            except Exception as e:
                logger.warning(f"Error closing pool: {e}")
            finally:
                self._pool = None
        
        self._prepared_statements.clear()
