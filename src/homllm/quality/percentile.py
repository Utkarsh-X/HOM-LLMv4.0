"""
Percentile-based normalization engine.

Rolling window of metric values for threshold-free anomaly detection.
No hard-coded thresholds — all comparison is relative to observed history.
"""

from __future__ import annotations

import json
from bisect import bisect_left
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class PercentileWindow:
    """
    Rolling window for percentile-based anomaly detection.

    Thread-safety: NOT thread-safe. External synchronization required
    if used from multiple threads.
    """

    max_size: int = 500
    _values: deque = field(default_factory=deque, repr=False)
    _sorted_cache: Optional[list[float]] = field(default=None, repr=False)

    def add(self, value: float) -> None:
        """Add a value to the window, evicting oldest if full."""
        self._values.append(value)
        if len(self._values) > self.max_size:
            self._values.popleft()
        self._sorted_cache = None  # Invalidate cache

    def percentile(self, value: float) -> float:
        """
        Position of value within the window.

        Returns:
            Float in [0.0, 1.0]. 0.5 during cold start (empty window).
        """
        if not self._values:
            return 0.5  # Cold start: assume median
        if self._sorted_cache is None:
            self._sorted_cache = sorted(self._values)
        rank = bisect_left(self._sorted_cache, value)
        return rank / len(self._sorted_cache)

    @property
    def count(self) -> int:
        """Number of values in the window."""
        return len(self._values)

    @property
    def is_reliable(self) -> bool:
        """Whether the window has enough data for meaningful percentiles."""
        return len(self._values) >= 30

    def to_dict(self) -> dict:
        """Serialize for persistence."""
        return {
            "max_size": self.max_size,
            "values": list(self._values),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PercentileWindow":
        """Deserialize from persistence."""
        window = cls(max_size=data.get("max_size", 500))
        for v in data.get("values", []):
            window._values.append(v)
        return window


METRIC_NAMES = (
    "semantic_strength",
    "query_term_recall",
    "file_entropy",
    "content_overlap",
    "score_separation",
    "reranker_influence",
    "budget_utilization",
)


@dataclass
class PercentileTracker:
    """
    Manages per-metric percentile windows.

    Provides a single entry point for adding metrics and querying percentiles.
    """

    max_size: int = 500
    windows: dict[str, PercentileWindow] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in METRIC_NAMES:
            if name not in self.windows:
                self.windows[name] = PercentileWindow(max_size=self.max_size)

    def add(self, metric_name: str, value: float) -> None:
        """Add a value to the named metric's window."""
        if metric_name not in self.windows:
            self.windows[metric_name] = PercentileWindow(max_size=self.max_size)
        self.windows[metric_name].add(value)

    def percentile(self, metric_name: str, value: float) -> float:
        """Get percentile position for a value in the named metric's window."""
        if metric_name not in self.windows:
            return 0.5  # No history
        return self.windows[metric_name].percentile(value)

    def save(self, path: Path) -> None:
        """Persist all windows to JSON."""
        data = {name: w.to_dict() for name, w in self.windows.items()}
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    @classmethod
    def load(cls, path: Path, max_size: int = 500) -> "PercentileTracker":
        """Load windows from JSON. Returns fresh tracker if file missing."""
        if not path.exists():
            return cls(max_size=max_size)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        tracker = cls(max_size=max_size)
        for name, w_data in data.items():
            tracker.windows[name] = PercentileWindow.from_dict(w_data)
        return tracker
