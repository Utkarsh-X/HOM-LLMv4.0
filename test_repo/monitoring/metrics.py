"""
Metrics collection and aggregation system.
Collects metrics for performance monitoring and observability.
"""

import time
import logging
from typing import Dict, Any, List, Optional
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

class MetricType(Enum):
    """Types of metrics."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"

@dataclass
class Metric:
    """Represents a single metric."""
    name: str
    metric_type: MetricType
    value: float
    timestamp: float = field(default_factory=time.time)
    labels: Dict[str, str] = field(default_factory=dict)
    unit: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.metric_type.value,
            "value": self.value,
            "timestamp": self.timestamp,
            "labels": self.labels,
            "unit": self.unit
        }

class MetricsCollector:
    """
    Collects and aggregates metrics with:
    - Multiple metric types
    - Label support
    - Aggregation over time windows
    - Export capabilities
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, retention_hours: int = 24):
        """Initialize metrics collector."""
        if self._initialized:
            return
        
        self.retention_hours = retention_hours
        self.metrics: List[Metric] = []
        self.counters: Dict[str, float] = defaultdict(float)
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        self.timers: Dict[str, List[float]] = defaultdict(list)
        self._initialized = True
        
        logger.info("MetricsCollector initialized")
    
    def increment_counter(self, name: str, amount: float = 1.0,
                         labels: Optional[Dict[str, str]] = None):
        """Increment a counter metric."""
        metric_key = self._make_key(name, labels)
        self.counters[metric_key] += amount
        
        metric = Metric(
            name=name,
            metric_type=MetricType.COUNTER,
            value=amount,
            labels=labels or {}
        )
        self.metrics.append(metric)
    
    def set_gauge(self, name: str, value: float,
                 labels: Optional[Dict[str, str]] = None):
        """Set a gauge metric."""
        metric_key = self._make_key(name, labels)
        self.gauges[metric_key] = value
        
        metric = Metric(
            name=name,
            metric_type=MetricType.GAUGE,
            value=value,
            labels=labels or {}
        )
        self.metrics.append(metric)
    
    def record_histogram(self, name: str, value: float,
                        labels: Optional[Dict[str, str]] = None):
        """Record a histogram value."""
        metric_key = self._make_key(name, labels)
        self.histograms[metric_key].append(value)
        
        metric = Metric(
            name=name,
            metric_type=MetricType.HISTOGRAM,
            value=value,
            labels=labels or {}
        )
        self.metrics.append(metric)
    
    def record_timer(self, name: str, duration_ms: float,
                    labels: Optional[Dict[str, str]] = None):
        """Record a timer value (in milliseconds)."""
        metric_key = self._make_key(name, labels)
        self.timers[metric_key].append(duration_ms)
        
        metric = Metric(
            name=name,
            metric_type=MetricType.TIMER,
            value=duration_ms,
            unit="ms",
            labels=labels or {}
        )
        self.metrics.append(metric)
    
    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get counter value."""
        metric_key = self._make_key(name, labels)
        return self.counters.get(metric_key, 0.0)
    
    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[float]:
        """Get gauge value."""
        metric_key = self._make_key(name, labels)
        return self.gauges.get(metric_key)
    
    def get_histogram_stats(self, name: str,
                           labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """Get histogram statistics."""
        metric_key = self._make_key(name, labels)
        values = self.histograms.get(metric_key, [])
        
        if not values:
            return {}
        
        sorted_values = sorted(values)
        return {
            "count": len(values),
            "sum": sum(values),
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "p50": sorted_values[len(sorted_values) // 2],
            "p95": sorted_values[int(len(sorted_values) * 0.95)],
            "p99": sorted_values[int(len(sorted_values) * 0.99)]
        }
    
    def get_timer_stats(self, name: str,
                       labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """Get timer statistics."""
        metric_key = self._make_key(name, labels)
        durations = self.timers.get(metric_key, [])
        
        if not durations:
            return {}
        
        sorted_durations = sorted(durations)
        return {
            "count": len(durations),
            "total_ms": sum(durations),
            "mean_ms": sum(durations) / len(durations),
            "min_ms": min(durations),
            "max_ms": max(durations),
            "p50_ms": sorted_durations[len(sorted_durations) // 2],
            "p95_ms": sorted_durations[int(len(sorted_durations) * 0.95)],
            "p99_ms": sorted_durations[int(len(sorted_durations) * 0.99)]
        }
    
    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """Create metric key from name and labels."""
        if not labels:
            return name
        
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all collected metrics."""
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "histogram_stats": {
                key: self.get_histogram_stats(key.split("{")[0])
                for key in self.histograms.keys()
            },
            "timer_stats": {
                key: self.get_timer_stats(key.split("{")[0])
                for key in self.timers.keys()
            }
        }
    
    def reset(self):
        """Reset all metrics."""
        self.metrics.clear()
        self.counters.clear()
        self.gauges.clear()
        self.histograms.clear()
        self.timers.clear()
        logger.info("Metrics reset")

