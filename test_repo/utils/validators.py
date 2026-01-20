"""
Input validation utilities.
These functions validate user input in API routes.
Creates duplicate logic traps - similar validation in multiple places.
"""

import re
import os
from pathlib import Path
from typing import Optional, List

def validate_query(query: str, min_length: int = 1, max_length: int = 500) -> tuple[bool, Optional[str]]:
    """
    Validate a search query string.
    Used in API routes to validate user input.
    
    Args:
        query: Query string to validate
        min_length: Minimum query length
        max_length: Maximum query length
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not query or not isinstance(query, str):
        return False, "Query must be a non-empty string"
    
    if len(query.strip()) < min_length:
        return False, f"Query must be at least {min_length} characters"
    
    if len(query) > max_length:
        return False, f"Query must be at most {max_length} characters"
    
    # Check for potentially dangerous patterns
    dangerous_patterns = [
        r'<script',
        r'javascript:',
        r'on\w+\s*=',
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return False, "Query contains potentially dangerous content"
    
    return True, None

def validate_file_path(file_path: str, must_exist: bool = False) -> tuple[bool, Optional[str]]:
    """
    Validate a file path.
    
    Args:
        file_path: File path to validate
        must_exist: Whether file must exist
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not file_path or not isinstance(file_path, str):
        return False, "File path must be a non-empty string"
    
    # Check for path traversal attempts
    if '..' in file_path or file_path.startswith('/'):
        return False, "Invalid file path"
    
    # Check if file exists (if required)
    if must_exist and not os.path.exists(file_path):
        return False, "File does not exist"
    
    # Check file extension
    path_obj = Path(file_path)
    if not path_obj.suffix:
        return False, "File must have an extension"
    
    return True, None

def validate_token_format(token: str) -> tuple[bool, Optional[str]]:
    """
    Validate JWT token format (basic format check, not signature).
    
    Args:
        token: JWT token string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not token or not isinstance(token, str):
        return False, "Token must be a non-empty string"
    
    # JWT tokens have 3 parts separated by dots
    parts = token.split('.')
    if len(parts) != 3:
        return False, "Invalid token format (must have 3 parts)"
    
    # Each part should be base64-like (simplified check)
    for part in parts:
        if not part or len(part) < 10:
            return False, "Invalid token format (parts too short)"
    
    return True, None

def validate_email(email: str) -> tuple[bool, Optional[str]]:
    """
    Validate email address format.
    
    Args:
        email: Email address string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not email or not isinstance(email, str):
        return False, "Email must be a non-empty string"
    
    # Basic email regex
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False, "Invalid email format"
    
    return True, None

def validate_user_id(user_id: str) -> tuple[bool, Optional[str]]:
    """
    Validate user ID format.
    
    Args:
        user_id: User ID string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not user_id or not isinstance(user_id, str):
        return False, "User ID must be a non-empty string"
    
    # User ID should be alphanumeric, 3-50 characters
    if not re.match(r'^[a-zA-Z0-9_-]{3,50}$', user_id):
        return False, "User ID must be 3-50 alphanumeric characters"
    
    return True, None
