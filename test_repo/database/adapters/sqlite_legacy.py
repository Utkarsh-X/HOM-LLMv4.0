"""
Legacy SQLite database adapter (synchronous).
This is the old implementation kept for backward compatibility.
Both this and PostgresAdapter have connect(), query(), and close() methods,
creating a name collision trap for RAG systems.
"""

import sqlite3
from typing import List, Dict, Any, Optional
from config import settings
from core.interfaces import IDatabaseAdapter
from core.exceptions import ConnectionError, DatabaseError

class SQLiteLegacyAdapter(IDatabaseAdapter):
    """
    Legacy synchronous SQLite database adapter.
    Old implementation using sqlite3 (not thread-safe).
    """
    
    def __init__(self):
        """Initialize the SQLite adapter."""
        self.db_path = settings.SQLITE_DB_PATH
        self.timeout = settings.DB_TIMEOUT  # Also uses config, but different implementation
        self._conn: Optional[sqlite3.Connection] = None
    
    def connect(self) -> None:
        """
        Establish synchronous connection to SQLite.
        Uses timeout from config.settings.DB_TIMEOUT for connection timeout.
        Note: This is NOT thread-safe (legacy code).
        """
        try:
            self._conn = sqlite3.connect(
                self.db_path,
                timeout=self.timeout,  # Uses config.settings.DB_TIMEOUT
                check_same_thread=False  # Legacy: not thread-safe
            )
            self._conn.row_factory = sqlite3.Row
        except Exception as e:
            raise ConnectionError(f"Failed to connect to SQLite: {e}")
    
    def query(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a SQL query (synchronous).
        
        Args:
            sql: SQL query string
            params: Optional query parameters
            
        Returns:
            List of result dictionaries
        """
        if not self._conn:
            raise ConnectionError("Not connected to database")
        
        try:
            cursor = self._conn.cursor()
            if params:
                cursor.execute(sql, tuple(params.values()))
            else:
                cursor.execute(sql)
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            raise DatabaseError(f"Query failed: {e}")
    
    def get_timeout(self) -> int:
        """Get the connection timeout value from config."""
        return settings.DB_TIMEOUT
    
    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
