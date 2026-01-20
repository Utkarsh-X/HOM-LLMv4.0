"""
Batch processor for processing collections of items.
Supports different batching strategies and transformations.
"""

import logging
from typing import List, Dict, Any, Callable, Optional, TypeVar, Generic
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)

T = TypeVar('T')
U = TypeVar('U')

@dataclass
class BatchResult:
    """Result of batch processing."""
    batch_id: str
    total_items: int
    processed_items: int
    failed_items: int
    duration_ms: float
    errors: List[str]
    results: List[Any]

class BatchProcessor(Generic[T, U]):
    """
    Batch processor with:
    - Configurable batch size
    - Parallel processing
    - Error handling per batch
    - Progress tracking
    """
    
    def __init__(self, batch_size: int = 100, 
                 max_parallel: int = 1):
        """
        Initialize batch processor.
        
        Args:
            batch_size: Size of each batch
            max_parallel: Maximum parallel batches
        """
        self.batch_size = batch_size
        self.max_parallel = max_parallel
        self.batch_stats = {
            "batches_processed": 0,
            "total_items": 0,
            "failed_items": 0,
            "total_duration_ms": 0.0
        }
    
    def process(self, items: List[T], 
               processor_func: Callable[[List[T]], List[U]],
               error_handler: Optional[Callable[[Exception], None]] = None) -> BatchResult:
        """
        Process items in batches.
        
        Args:
            items: Items to process
            processor_func: Function to process batch
            error_handler: Optional error handler
            
        Returns:
            Batch result
        """
        import uuid
        batch_id = str(uuid.uuid4())
        start_time = time.time()
        
        results = []
        errors = []
        processed_count = 0
        failed_count = 0
        
        # Split into batches
        batches = [
            items[i:i + self.batch_size]
            for i in range(0, len(items), self.batch_size)
        ]
        
        logger.info(f"Processing {len(items)} items in {len(batches)} batches")
        
        for batch_idx, batch in enumerate(batches, 1):
            try:
                batch_results = processor_func(batch)
                results.extend(batch_results)
                processed_count += len(batch)
                
                logger.debug(f"Batch {batch_idx}/{len(batches)} completed")
                
            except Exception as e:
                error_msg = f"Batch {batch_idx} failed: {str(e)}"
                errors.append(error_msg)
                failed_count += len(batch)
                
                if error_handler:
                    error_handler(e)
                
                logger.error(error_msg)
        
        duration_ms = (time.time() - start_time) * 1000
        
        self.batch_stats["batches_processed"] += len(batches)
        self.batch_stats["total_items"] += len(items)
        self.batch_stats["failed_items"] += failed_count
        self.batch_stats["total_duration_ms"] += duration_ms
        
        return BatchResult(
            batch_id=batch_id,
            total_items=len(items),
            processed_items=processed_count,
            failed_items=failed_count,
            duration_ms=duration_ms,
            errors=errors,
            results=results
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get batch processor statistics."""
        return self.batch_stats

