"""
Worker pool for executing async jobs.
Manages worker threads and job distribution.
"""

import logging
import threading
import time
from typing import Dict, Any, Callable, Optional, List
from async_jobs.job_queue import JobQueue, Job, JobStatus

logger = logging.getLogger(__name__)

class Worker(threading.Thread):
    """Worker thread that processes jobs from the queue."""
    
    def __init__(self, worker_id: str, job_queue: JobQueue,
                 task_handlers: Dict[str, Callable]):
        """
        Initialize worker.
        
        Args:
            worker_id: Worker ID
            job_queue: Job queue to process from
            task_handlers: Mapping of task names to handler functions
        """
        super().__init__(daemon=True)
        self.worker_id = worker_id
        self.job_queue = job_queue
        self.task_handlers = task_handlers
        self.running = True
        self.processed_jobs = 0
        self.failed_jobs = 0
    
    def run(self):
        """Worker main loop."""
        logger.info(f"Worker {self.worker_id} started")
        
        while self.running:
            try:
                job = self.job_queue.dequeue()
                if not job:
                    time.sleep(0.1)  # Wait before retry
                    continue
                
                # Get task handler
                handler = self.task_handlers.get(job.task_name)
                if not handler:
                    self.job_queue.fail_job(
                        job.job_id,
                        f"No handler for task: {job.task_name}"
                    )
                    self.failed_jobs += 1
                    continue
                
                # Execute job
                try:
                    logger.info(f"Worker {self.worker_id} executing {job.job_id}")
                    result = handler(job.payload)
                    self.job_queue.complete_job(job.job_id, result)
                    self.processed_jobs += 1
                    
                except Exception as e:
                    self.job_queue.fail_job(job.job_id, str(e))
                    self.failed_jobs += 1
                    logger.error(f"Job {job.job_id} failed: {e}")
                    
            except Exception as e:
                logger.error(f"Worker {self.worker_id} error: {e}")
                time.sleep(1)
        
        logger.info(f"Worker {self.worker_id} stopped")
    
    def stop(self):
        """Stop worker."""
        self.running = False

class WorkerPool:
    """
    Pool of worker threads.
    Manages worker lifecycle and job distribution.
    """
    
    def __init__(self, num_workers: int = 4,
                 task_handlers: Optional[Dict[str, Callable]] = None):
        """
        Initialize worker pool.
        
        Args:
            num_workers: Number of worker threads
            task_handlers: Mapping of task names to handlers
        """
        self.num_workers = num_workers
        self.task_handlers = task_handlers or {}
        self.job_queue = JobQueue()
        self.workers: List[Worker] = []
        self.started = False
        self.pool_stats = {
            "total_workers": num_workers,
            "total_jobs_processed": 0,
            "total_jobs_failed": 0
        }
    
    def start(self):
        """Start all workers."""
        if self.started:
            return
        
        for i in range(self.num_workers):
            worker = Worker(
                f"worker_{i}",
                self.job_queue,
                self.task_handlers
            )
            worker.start()
            self.workers.append(worker)
        
        self.started = True
        logger.info(f"Started worker pool with {self.num_workers} workers")
    
    def stop(self):
        """Stop all workers."""
        for worker in self.workers:
            worker.stop()
        
        for worker in self.workers:
            worker.join(timeout=5)
        
        self.started = False
        logger.info("Stopped all workers")
    
    def submit_job(self, task_name: str, payload: Dict[str, Any],
                  priority: int = 5, max_retries: int = 3) -> str:
        """
        Submit a job to the pool.
        
        Args:
            task_name: Task name
            payload: Task payload
            priority: Job priority
            max_retries: Maximum retries
            
        Returns:
            Job ID
        """
        return self.job_queue.enqueue(
            task_name,
            payload,
            priority=priority,
            max_retries=max_retries
        )
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status."""
        job = self.job_queue.get_job(job_id)
        return job.to_dict() if job else None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        queue_stats = self.job_queue.get_stats()
        
        total_processed = sum(w.processed_jobs for w in self.workers)
        total_failed = sum(w.failed_jobs for w in self.workers)
        
        return {
            "pool_size": self.num_workers,
            "started": self.started,
            "queue_stats": queue_stats,
            "total_jobs_processed": total_processed,
            "total_jobs_failed": total_failed,
            "worker_stats": [
                {
                    "worker_id": w.worker_id,
                    "processed": w.processed_jobs,
                    "failed": w.failed_jobs
                }
                for w in self.workers
            ]
        }

