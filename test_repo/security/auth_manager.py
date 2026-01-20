"""
JWT-based authentication manager.
Handles token generation, validation, and user authentication.
"""

import jwt
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from config import settings
from core.exceptions import InvalidTokenError, AuthenticationError

class AuthManager:
    """
    Manages JWT-based authentication.
    Uses HS256 algorithm with configurable expiration.
    """
    
    def __init__(self):
        """Initialize the authentication manager."""
        self.secret_key = settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.expiration_hours = settings.JWT_EXPIRATION_HOURS
    
    def generate_token(self, user_id: str, username: str, is_admin: bool = False) -> str:
        """
        Generate a JWT token for a user.
        
        Args:
            user_id: Unique user identifier
            username: Username
            is_admin: Whether user has admin privileges
            
        Returns:
            Encoded JWT token string
        """
        payload = {
            "user_id": user_id,
            "username": username,
            "is_admin": is_admin,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=self.expiration_hours)
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate and decode a JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded token payload
            
        Raises:
            InvalidTokenError: If token is invalid, expired, or malformed
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise InvalidTokenError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise InvalidTokenError(f"Invalid token: {e}")
        except Exception as e:
            raise InvalidTokenError(f"Token validation failed: {e}")
    
    def get_user_from_token(self, token: str) -> Dict[str, Any]:
        """
        Extract user information from a token.
        
        Args:
            token: JWT token string
            
        Returns:
            User information dictionary
        """
        payload = self.validate_token(token)
        return {
            "user_id": payload.get("user_id"),
            "username": payload.get("username"),
            "is_admin": payload.get("is_admin", False)
        }
    
    def is_admin(self, token: str) -> bool:
        """
        Check if token belongs to an admin user.
        
        Args:
            token: JWT token string
            
        Returns:
            True if user is admin, False otherwise
        """
        try:
            payload = self.validate_token(token)
            return payload.get("is_admin", False)
        except InvalidTokenError:
            return False
