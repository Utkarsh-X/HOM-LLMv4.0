"""
Database module containing connection management and adapters.
"""

from database.connection import ConnectionPool
from database.adapters.postgres import PostgresAdapter
from database.adapters.sqlite_legacy import SQLiteLegacyAdapter

__all__ = ["ConnectionPool", "PostgresAdapter", "SQLiteLegacyAdapter"]
