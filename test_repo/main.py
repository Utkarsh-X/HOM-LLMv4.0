"""
Main entry point for the Secure Document Search API.
Simplified entry point that relies on imports from the new architecture.
"""

import sys
from typing import Optional
from api.routes import search_endpoint, admin_search_endpoint, index_endpoint
from api.dependencies import get_database, get_search_engine
from security.auth_manager import AuthManager
from config import settings

def greet():
    """Prints a welcome message."""
    print("Welcome to the Secure Document Search API!")
    print(f"API running on {settings.API_HOST}:{settings.API_PORT}")

def run_search(query: str, token: Optional[str] = None, admin: bool = False):
    """
    Run a search query.
    
    Args:
        query: Search query string
        token: Optional JWT token (for testing)
        admin: Whether to use admin endpoint
    """
    try:
        if admin:
            result = admin_search_endpoint(query, token=token, user={})
        else:
            result = search_endpoint(query, token=token, user={})
        print(f"Results: {result}")
    except Exception as e:
        print(f"Error: {e}")

def main():
    """Main CLI entry point."""
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "search":
            query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
            if query:
                # Generate a test token
                auth_manager = AuthManager()
                token = auth_manager.generate_token("user1", "testuser", is_admin=False)
                run_search(query, token=token)
            else:
                print("Usage: python main.py search <query>")
        
        elif command == "admin-search":
            query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
            if query:
                auth_manager = AuthManager()
                token = auth_manager.generate_token("admin1", "admin", is_admin=True)
                run_search(query, token=token, admin=True)
            else:
                print("Usage: python main.py admin-search <query>")
        
        elif command == "index":
            file_path = sys.argv[2] if len(sys.argv) > 2 else ""
            if file_path:
                auth_manager = AuthManager()
                token = auth_manager.generate_token("user1", "testuser", is_admin=False)
                result = index_endpoint(file_path, token=token, user={})
                print(f"Indexing result: {result}")
            else:
                print("Usage: python main.py index <file_path>")
        
        else:
            print("Usage: python main.py [search <query> | admin-search <query> | index <file_path>]")
    else:
        greet()

if __name__ == "__main__":
    main()
