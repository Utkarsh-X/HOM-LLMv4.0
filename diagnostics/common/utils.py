"""
Common utility functions for diagnostic framework.

All utilities are pure functions with no side effects on core system.
"""

from pathlib import Path
from typing import Sequence
import statistics


def parse_query_selector(selector: str) -> list[int]:
    """
    Parse a query selector string into a list of query IDs.
    
    Supported formats:
    - Single: "3" -> [3]
    - List: "1,5,7" -> [1, 5, 7]
    - Range: "1-10" -> [1, 2, 3, ..., 10]
    - All: "all" -> [] (empty means all)
    
    Returns:
        List of query IDs, or empty list for "all"
    """
    selector = selector.strip().lower()
    
    if selector == "all":
        return []
    
    if "-" in selector and "," not in selector:
        # Range format: "1-10"
        parts = selector.split("-")
        if len(parts) == 2:
            try:
                start = int(parts[0])
                end = int(parts[1])
                return list(range(start, end + 1))
            except ValueError:
                pass
    
    if "," in selector:
        # List format: "1,5,7"
        try:
            return [int(x.strip()) for x in selector.split(",")]
        except ValueError:
            pass
    
    # Single format: "3"
    try:
        return [int(selector)]
    except ValueError:
        return []


def ensure_reports_dir(base_path: Path, subdir: str = "") -> Path:
    """
    Ensure reports directory exists.
    
    Args:
        base_path: Base diagnostics path
        subdir: Subdirectory (per_query or summary)
    
    Returns:
        Path to reports directory
    """
    reports_path = base_path / "reports" / subdir if subdir else base_path / "reports"
    reports_path.mkdir(parents=True, exist_ok=True)
    return reports_path


def compute_percentile(values: Sequence[float], percentile: float) -> float:
    """
    Compute percentile of a sequence of values.
    
    Args:
        values: Sequence of numeric values
        percentile: Percentile to compute (0-100)
    
    Returns:
        Percentile value, or 0.0 if empty
    """
    if not values:
        return 0.0
    
    sorted_values = sorted(values)
    n = len(sorted_values)
    
    if n == 1:
        return sorted_values[0]
    
    # Linear interpolation
    k = (percentile / 100.0) * (n - 1)
    f = int(k)
    c = f + 1 if f + 1 < n else f
    
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


def compute_overlap_ratio(set_a: set, set_b: set) -> float:
    """
    Compute Jaccard-like overlap ratio between two sets.
    
    Returns:
        Overlap ratio (0.0 to 1.0)
    """
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def compute_rank_correlation(ranks_a: list[str], ranks_b: list[str]) -> float:
    """
    Compute rank correlation between two ranked lists.
    
    Uses a simplified Kendall's tau based on position differences.
    
    Args:
        ranks_a: First ranked list (doc IDs)
        ranks_b: Second ranked list (doc IDs)
    
    Returns:
        Correlation score (-1.0 to 1.0)
    """
    if not ranks_a or not ranks_b:
        return 0.0
    
    # Create position maps
    pos_a = {doc: i for i, doc in enumerate(ranks_a)}
    pos_b = {doc: i for i, doc in enumerate(ranks_b)}
    
    # Find common docs
    common = set(ranks_a) & set(ranks_b)
    if len(common) < 2:
        return 0.0
    
    # Count concordant and discordant pairs
    concordant = 0
    discordant = 0
    common_list = list(common)
    
    for i in range(len(common_list)):
        for j in range(i + 1, len(common_list)):
            doc_i, doc_j = common_list[i], common_list[j]
            
            diff_a = pos_a[doc_i] - pos_a[doc_j]
            diff_b = pos_b[doc_i] - pos_b[doc_j]
            
            if diff_a * diff_b > 0:
                concordant += 1
            elif diff_a * diff_b < 0:
                discordant += 1
    
    total = concordant + discordant
    if total == 0:
        return 1.0
    
    return (concordant - discordant) / total


def format_bytes(size_bytes: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}TB"


def format_duration(ms: float) -> str:
    """Format milliseconds to human-readable duration."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    if ms < 60000:
        return f"{ms/1000:.1f}s"
    return f"{ms/60000:.1f}m"


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers, returning default on zero division."""
    if denominator == 0:
        return default
    return numerator / denominator
