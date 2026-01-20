"""
Monitoring decorators for tracing and metrics.
"""

from functools import wraps
from typing import Callable, Optional, Dict, Any
import time
from monitoring.tracer import Tracer
from monitoring.metrics import MetricsCollector

tracer = Tracer()
metrics = MetricsCollector()

def trace(operation_name: Optional[str] = None, tags: Optional[Dict[str, Any]] = None):
    """
    Decorator to trace function execution.
    
    Usage:
        @trace("database_query", tags={"db": "postgres"})
        def query_database():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            span = tracer.start_span(op_name, tags=tags)
            
            try:
                result = func(*args, **kwargs)
                span.add_tag("status", "success")
                return result
            except Exception as e:
                span.add_tag("status", "error")
                span.set_error(str(e))
                raise
            finally:
                tracer.end_span(span)
        
        return wrapper
    return decorator

def measure(metric_name: Optional[str] = None,
           labels: Optional[Dict[str, str]] = None):
    """
    Decorator to measure function execution time and count.
    
    Usage:
        @measure("search_duration", labels={"query_type": "semantic"})
        def search(query):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            name = metric_name or func.__name__
            
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                
                metrics.increment_counter(f"{name}_count", labels=labels)
                metrics.record_timer(f"{name}_duration", duration_ms, labels=labels)
                
                return result
            except Exception as e:
                metrics.increment_counter(f"{name}_errors", labels=labels)
                raise
        
        return wrapper
    return decorator

