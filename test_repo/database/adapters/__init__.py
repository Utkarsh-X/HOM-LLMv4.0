"""
Database adapters for different database backends.
"""

from database.adapters.postgres import PostgresAdapter
from database.adapters.sqlite_legacy import SQLiteLegacyAdapter

__all__ = ["PostgresAdapter", "SQLiteLegacyAdapter"]
