"""
Distributed tracing system.
Tracks request flow through the system with spans and context propagation.
"""

import time
import uuid
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import json
import threading

logger = logging.getLogger(__name__)

@dataclass
class Span:
    """Represents a single traced operation."""
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: float = 0.0
    tags: Dict[str, Any] = None
    logs: List[Dict[str, Any]] = None
    status: str = "active"
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = {}
        if self.logs is None:
            self.logs = []
    
    def finish(self):
        """Mark span as finished."""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.status = "finished"
    
    def set_error(self, error: str):
        """Mark span with error."""
        self.error = error
        self.status = "error"
    
    def add_tag(self, key: str, value: Any):
        """Add tag to span."""
        self.tags[key] = value
    
    def add_log(self, message: str, level: str = "info"):
        """Add log entry to span."""
        self.logs.append({
            "timestamp": time.time(),
            "message": message,
            "level": level
        })
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["start_time"] = datetime.fromtimestamp(self.start_time).isoformat()
        if self.end_time:
            data["end_time"] = datetime.fromtimestamp(self.end_time).isoformat()
        return data

class TraceContext:
    """Thread-local trace context."""
    _context = threading.local()
    
    @classmethod
    def set_trace_id(cls, trace_id: str):
        cls._context.trace_id = trace_id
    
    @classmethod
    def get_trace_id(cls) -> str:
        return getattr(cls._context, 'trace_id', None)
    
    @classmethod
    def set_span_id(cls, span_id: str):
        cls._context.span_id = span_id
    
    @classmethod
    def get_span_id(cls) -> str:
        return getattr(cls._context, 'span_id', None)
    
    @classmethod
    def clear(cls):
        if hasattr(cls._context, 'trace_id'):
            delattr(cls._context, 'trace_id')
        if hasattr(cls._context, 'span_id'):
            delattr(cls._context, 'span_id')

class Tracer:
    """
    Distributed tracer with:
    - Trace and span management
    - Context propagation
    - Span relationship tracking
    - Export capabilities
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, service_name: str = "search-api"):
        """Initialize tracer."""
        if self._initialized:
            return
        
        self.service_name = service_name
        self.traces: Dict[str, List[Span]] = {}
        self.active_spans: Dict[str, Span] = {}
        self._lock = threading.Lock()
        self._initialized = True
        
        logger.info(f"Tracer initialized for service: {service_name}")
    
    def start_trace(self) -> str:
        """
        Start a new trace.
        
        Returns:
            Trace ID
        """
        trace_id = str(uuid.uuid4())
        self.traces[trace_id] = []
        TraceContext.set_trace_id(trace_id)
        
        logger.debug(f"Started trace: {trace_id}")
        return trace_id
    
    def start_span(self, operation_name: str, tags: Optional[Dict[str, Any]] = None) -> Span:
        """
        Start a new span.
        
        Args:
            operation_name: Name of the operation
            tags: Optional tags
            
        Returns:
            Span object
        """
        trace_id = TraceContext.get_trace_id() or self.start_trace()
        parent_span_id = TraceContext.get_span_id()
        
        span_id = str(uuid.uuid4())
        span = Span(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            start_time=time.time(),
            tags=tags or {}
        )
        
        with self._lock:
            if trace_id not in self.traces:
                self.traces[trace_id] = []
            self.traces[trace_id].append(span)
            self.active_spans[span_id] = span
        
        TraceContext.set_span_id(span_id)
        
        logger.debug(f"Started span {span_id} for operation: {operation_name}")
        return span
    
    def end_span(self, span: Span, error: Optional[str] = None):
        """
        End a span.
        
        Args:
            span: Span to end
            error: Optional error message
        """
        span.finish()
        if error:
            span.set_error(error)
        
        with self._lock:
            if span.span_id in self.active_spans:
                del self.active_spans[span.span_id]
        
        # Restore parent span context
        if span.parent_span_id:
            TraceContext.set_span_id(span.parent_span_id)
        else:
            TraceContext.set_span_id(None)
        
        logger.debug(f"Ended span {span.span_id}: {span.status}")
    
    def get_trace(self, trace_id: str) -> Optional[List[Span]]:
        """Get trace by ID."""
        return self.traces.get(trace_id)
    
    def export_trace(self, trace_id: str) -> str:
        """Export trace as JSON."""
        spans = self.get_trace(trace_id)
        if not spans:
            return "{}"
        
        trace_data = {
            "trace_id": trace_id,
            "service": self.service_name,
            "span_count": len(spans),
            "spans": [span.to_dict() for span in spans]
        }
        
        return json.dumps(trace_data, indent=2)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get tracer statistics."""
        return {
            "total_traces": len(self.traces),
            "active_spans": len(self.active_spans),
            "service": self.service_name
        }

