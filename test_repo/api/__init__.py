"""
API layer for the Secure Document Search API.
"""

from api.routes import search_endpoint, admin_search_endpoint, index_endpoint
from api.dependencies import get_database, get_search_engine, get_current_user

__all__ = [
    "search_endpoint",
    "admin_search_endpoint",
    "index_endpoint",
    "get_database",
    "get_search_engine",
    "get_current_user"
]
