"""
Password hashing utilities using bcrypt-like algorithm.
This module handles password hashing and verification.
"""

import hashlib
import secrets
from config import settings

def hash_password(password: str) -> str:
    """
    Hash a password using SHA-256 with salt.
    In production, this would use bcrypt with settings.BCRYPT_ROUNDS.
    
    Args:
        password: Plain text password
        
    Returns:
        Hashed password string (salt:hash format)
    """
    # Generate salt
    salt = secrets.token_hex(16)
    
    # Hash password with salt
    hash_obj = hashlib.sha256()
    hash_obj.update((password + salt).encode('utf-8'))
    password_hash = hash_obj.hexdigest()
    
    # Return salt:hash format
    return f"{salt}:{password_hash}"

def verify_password(password: str, hashed: str) -> bool:
    """
    Verify a password against a hash.
    
    Args:
        password: Plain text password to verify
        hashed: Hashed password string (salt:hash format)
        
    Returns:
        True if password matches, False otherwise
    """
    try:
        salt, stored_hash = hashed.split(":", 1)
        
        # Hash the provided password with the stored salt
        hash_obj = hashlib.sha256()
        hash_obj.update((password + salt).encode('utf-8'))
        password_hash = hash_obj.hexdigest()
        
        # Compare hashes (constant-time comparison)
        return secrets.compare_digest(password_hash, stored_hash)
    except (ValueError, AttributeError):
        return False

def needs_rehash(hashed: str) -> bool:
    """
    Check if a password hash needs to be rehashed.
    This would check if the hash uses the current BCRYPT_ROUNDS setting.
    
    Args:
        hashed: Hashed password string
        
    Returns:
        True if rehashing is needed, False otherwise
    """
    # Simplified: always return False for this implementation
    # In production, would check if hash uses current BCRYPT_ROUNDS
    return False
