"""
String manipulation utilities.
High token count, low semantic value - creates "haystack" for RAG systems.
Many similar-sounding functions that can confuse retrieval.
"""

import re
from typing import List, Optional

def normalize_string(text: str) -> str:
    """
    Normalize a string by removing extra whitespace and converting to lowercase.
    
    Args:
        text: Input string
        
    Returns:
        Normalized string
    """
    return re.sub(r'\s+', ' ', text.strip().lower())

def sanitize_input(text: str) -> str:
    """
    Sanitize user input by removing potentially dangerous characters.
    
    Args:
        text: Input string
        
    Returns:
        Sanitized string
    """
    # Remove control characters and normalize
    sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    return sanitized.strip()

def extract_keywords(text: str, min_length: int = 3) -> List[str]:
    """
    Extract keywords from text.
    
    Args:
        text: Input text
        min_length: Minimum keyword length
        
    Returns:
        List of keywords
    """
    # Simple keyword extraction (split on whitespace and punctuation)
    words = re.findall(r'\b\w+\b', text.lower())
    keywords = [w for w in words if len(w) >= min_length]
    return list(set(keywords))  # Remove duplicates

def format_code_block(code: str, language: str = "python") -> str:
    """
    Format code as a code block string.
    
    Args:
        code: Code string
        language: Programming language
        
    Returns:
        Formatted code block string
    """
    return f"```{language}\n{code}\n```"

def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate a string to a maximum length.
    
    Args:
        text: Input string
        max_length: Maximum length
        suffix: Suffix to append if truncated
        
    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix

def split_camel_case(text: str) -> List[str]:
    """
    Split camelCase or PascalCase string into words.
    
    Args:
        text: CamelCase string
        
    Returns:
        List of words
    """
    # Insert space before uppercase letters
    spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    return spaced.split()

def remove_special_chars(text: str, keep_spaces: bool = True) -> str:
    """
    Remove special characters from string.
    
    Args:
        text: Input string
        keep_spaces: Whether to keep spaces
        
    Returns:
        String with special characters removed
    """
    if keep_spaces:
        return re.sub(r'[^a-zA-Z0-9\s]', '', text)
    else:
        return re.sub(r'[^a-zA-Z0-9]', '', text)

def count_words(text: str) -> int:
    """
    Count words in a string.
    
    Args:
        text: Input string
        
    Returns:
        Word count
    """
    words = re.findall(r'\b\w+\b', text)
    return len(words)

def find_substring(text: str, pattern: str, case_sensitive: bool = False) -> List[int]:
    """
    Find all occurrences of a substring pattern.
    
    Args:
        text: Input text
        pattern: Pattern to find
        case_sensitive: Whether search is case-sensitive
        
    Returns:
        List of start indices
    """
    if not case_sensitive:
        text = text.lower()
        pattern = pattern.lower()
    
    indices = []
    start = 0
    while True:
        idx = text.find(pattern, start)
        if idx == -1:
            break
        indices.append(idx)
        start = idx + 1
    
    return indices
