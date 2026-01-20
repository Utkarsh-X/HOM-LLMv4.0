"""
Date and time manipulation utilities.
Used for formatting timestamps in API responses and logs.
"""

from datetime import datetime, timezone
from typing import Optional

def format_timestamp(dt: Optional[datetime] = None, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format a datetime as a timestamp string.
    Used in API responses for date formatting.
    
    Args:
        dt: Datetime object (defaults to current time)
        format_str: Format string
        
    Returns:
        Formatted timestamp string
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    
    return dt.strftime(format_str)

def parse_date(date_string: str, format_str: str = "%Y-%m-%d") -> Optional[datetime]:
    """
    Parse a date string into a datetime object.
    
    Args:
        date_string: Date string
        format_str: Format string
        
    Returns:
        Datetime object or None if parsing fails
    """
    try:
        return datetime.strptime(date_string, format_str)
    except (ValueError, TypeError):
        return None

def get_current_time() -> datetime:
    """
    Get current UTC time.
    
    Returns:
        Current datetime in UTC
    """
    return datetime.now(timezone.utc)

def time_ago(dt: datetime) -> str:
    """
    Get human-readable "time ago" string.
    
    Args:
        dt: Past datetime
        
    Returns:
        Human-readable time difference string
    """
    now = datetime.now(timezone.utc)
    diff = now - dt
    
    if diff.days > 365:
        years = diff.days // 365
        return f"{years} year{'s' if years > 1 else ''} ago"
    elif diff.days > 30:
        months = diff.days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    elif diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "just now"

def is_weekend(dt: Optional[datetime] = None) -> bool:
    """
    Check if a date falls on a weekend.
    
    Args:
        dt: Datetime object (defaults to current time)
        
    Returns:
        True if weekend, False otherwise
    """
    if dt is None:
        dt = datetime.now()
    
    return dt.weekday() >= 5  # Saturday = 5, Sunday = 6
