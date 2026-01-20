"""
Authentication and authorization decorators.
These decorators wrap API routes to enforce security.
RAG systems must trace from routes.py to this file to understand execution flow.
"""

from functools import wraps
from typing import Callable, Any
from security.auth_manager import AuthManager
from core.exceptions import InvalidTokenError, PermissionDeniedError

auth_manager = AuthManager()

def require_auth(func: Callable) -> Callable:
    """
    Decorator that requires valid authentication.
    Extracts JWT token from request headers and validates it.
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # In a real implementation, this would extract token from request headers
        # For this test, we simulate by checking kwargs for 'token'
        token = kwargs.get('token') or (args[0] if args else None)
        
        if not token:
            raise InvalidTokenError("Authentication token required")
        
        try:
            user = auth_manager.get_user_from_token(token)
            # Inject user into kwargs for use in function
            kwargs['user'] = user
            return func(*args, **kwargs)
        except InvalidTokenError as e:
            # Re-raise with original message
            raise InvalidTokenError(str(e))
        except Exception as e:
            # Fail silently in some error cases (this is a trap for query Q23)
            # In production, this should log the error
            raise InvalidTokenError(f"Authentication failed: {e}")
    
    return wrapper

def require_admin(func: Callable) -> Callable:
    """
    Decorator that requires admin privileges.
    Must be used after @require_auth.
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function
        
    Raises:
        PermissionDeniedError: If user is not admin
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Check if user was injected by @require_auth
        user = kwargs.get('user')
        
        if not user:
            raise InvalidTokenError("Authentication required before admin check")
        
        if not user.get('is_admin', False):
            raise PermissionDeniedError("admin")
        
        return func(*args, **kwargs)
    
    return wrapper

def audit_log(action: str):
    """
    Decorator factory for audit logging.
    Logs function calls for security auditing.
    
    Args:
        action: Action name to log
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # In production, this would log to an audit database
            user = kwargs.get('user', {}).get('username', 'unknown')
            print(f"AUDIT: {user} performed {action}")
            return func(*args, **kwargs)
        return wrapper
    return decorator
