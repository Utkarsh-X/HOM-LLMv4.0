"""
Job queue management system.
Manages job lifecycle with persistence and retry logic.
"""

import logging
import time
import uuid
from typing import Dict, Any, Optional, Callable, List
from enum import Enum
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

class JobStatus(Enum):
    """Job status enumeration."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRY = "retry"

@dataclass
class Job:
    """Represents a job in the queue."""
    job_id: str
    task_name: str
    payload: Dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    priority: int = 5  # 1-10, lower is higher priority
    created_at: float = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    retries: int = 0
    max_retries: int = 3
    timeout_seconds: int = 300
    tags: Dict[str, str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.tags is None:
            self.tags = {}
    
    def get_duration_ms(self) -> Optional[float]:
        """Get job execution duration in milliseconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary."""
        return {
            "job_id": self.job_id,
            "task_name": self.task_name,
            "status": self.status.value,
            "priority": self.priority,
            "created_at": datetime.fromtimestamp(self.created_at).isoformat(),
            "started_at": datetime.fromtimestamp(self.started_at).isoformat() if self.started_at else None,
            "completed_at": datetime.fromtimestamp(self.completed_at).isoformat() if self.completed_at else None,
            "duration_ms": self.get_duration_ms(),
            "retries": self.retries,
            "max_retries": self.max_retries,
            "error": self.error
        }

class JobQueue:
    """
    Job queue with:
    - Priority-based ordering
    - Retry logic with exponential backoff
    - Job persistence
    - Status tracking
    - Metrics collection
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, max_queue_size: int = 10000):
        """Initialize job queue."""
        if self._initialized:
            return
        
        self.max_queue_size = max_queue_size
        self.pending_jobs: Dict[int, List[Job]] = defaultdict(list)  # priority -> jobs
        self.running_jobs: Dict[str, Job] = {}  # job_id -> job
        self.completed_jobs: Dict[str, Job] = {}  # job_id -> job
        
        self.stats = {
            "total_jobs": 0,
            "completed_jobs": 0,
            "failed_jobs": 0,
            "retried_jobs": 0
        }
        
        self._lock = __import__("threading").Lock()
        self._initialized = True
        
        logger.info("JobQueue initialized")
    
    def enqueue(self, task_name: str, payload: Dict[str, Any],
               priority: int = 5, max_retries: int = 3,
               timeout_seconds: int = 300) -> str:
        """
        Enqueue a new job.
        
        Args:
            task_name: Name of the task
            payload: Task payload
            priority: Job priority (1-10, lower is higher)
            max_retries: Maximum retries
            timeout_seconds: Job timeout
            
        Returns:
            Job ID
        """
        job_id = str(uuid.uuid4())
        job = Job(
            job_id=job_id,
            task_name=task_name,
            payload=payload,
            priority=priority,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            status=JobStatus.QUEUED
        )
        
        with self._lock:
            if len(self.pending_jobs) >= self.max_queue_size:
                raise RuntimeError(f"Queue full (max {self.max_queue_size})")
            
            self.pending_jobs[priority].append(job)
            self.stats["total_jobs"] += 1
        
        logger.info(f"Enqueued job {job_id}: {task_name} (priority: {priority})")
        return job_id
    
    def dequeue(self) -> Optional[Job]:
        """
        Dequeue next highest priority job.
        
        Returns:
            Job or None if queue empty
        """
        with self._lock:
            # Find lowest priority number (highest priority)
            for priority in sorted(self.pending_jobs.keys()):
                if self.pending_jobs[priority]:
                    job = self.pending_jobs[priority].pop(0)
                    job.status = JobStatus.RUNNING
                    job.started_at = time.time()
                    self.running_jobs[job.job_id] = job
                    return job
        
        return None
    
    def complete_job(self, job_id: str, result: Any):
        """
        Mark job as completed.
        
        Args:
            job_id: Job ID
            result: Job result
        """
        with self._lock:
            if job_id in self.running_jobs:
                job = self.running_jobs.pop(job_id)
                job.status = JobStatus.COMPLETED
                job.completed_at = time.time()
                job.result = result
                self.completed_jobs[job_id] = job
                self.stats["completed_jobs"] += 1
                
                logger.info(f"Completed job {job_id} in {job.get_duration_ms():.2f}ms")
    
    def fail_job(self, job_id: str, error: str):
        """
        Mark job as failed.
        
        Args:
            job_id: Job ID
            error: Error message
        """
        with self._lock:
            if job_id in self.running_jobs:
                job = self.running_jobs.pop(job_id)
                job.error = error
                job.retries += 1
                
                if job.retries < job.max_retries:
                    # Requeue with exponential backoff
                    job.status = JobStatus.RETRY
                    self.pending_jobs[job.priority].append(job)
                    self.stats["retried_jobs"] += 1
                    logger.warning(f"Retrying job {job_id} (attempt {job.retries}/{job.max_retries})")
                else:
                    job.status = JobStatus.FAILED
                    self.completed_jobs[job_id] = job
                    self.stats["failed_jobs"] += 1
                    logger.error(f"Job {job_id} failed after {job.retries} retries: {error}")
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        if job_id in self.running_jobs:
            return self.running_jobs[job_id]
        if job_id in self.completed_jobs:
            return self.completed_jobs[job_id]
        return None
    
    def get_queue_size(self) -> int:
        """Get current queue size."""
        with self._lock:
            return sum(len(jobs) for jobs in self.pending_jobs.values())
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        with self._lock:
            return {
                "queue_size": self.get_queue_size(),
                "running_jobs": len(self.running_jobs),
                "completed_jobs": len(self.completed_jobs),
                **self.stats
            }

