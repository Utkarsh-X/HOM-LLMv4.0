"""
Query execution engine.
Executes optimized query plans and manages execution context.
"""

import logging
import time
from typing import Dict, Any, List, Optional
from optimization.query_planner import QueryPlan, PlanOperation
from monitoring.tracer import Tracer
from monitoring.metrics import MetricsCollector

logger = logging.getLogger(__name__)
tracer = Tracer()
metrics = MetricsCollector()

class ExecutionContext:
    """Execution context for a query."""
    
    def __init__(self, query_id: str):
        """Initialize execution context."""
        self.query_id = query_id
        self.start_time = time.time()
        self.end_time = None
        self.rows_processed = 0
        self.execution_stages = []
        self.errors = []
    
    def finish(self):
        """Mark context as finished."""
        self.end_time = time.time()
    
    def get_duration_ms(self) -> float:
        """Get execution duration in milliseconds."""
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "query_id": self.query_id,
            "start_time": self.start_time,
            "duration_ms": self.get_duration_ms(),
            "rows_processed": self.rows_processed,
            "stages": self.execution_stages,
            "errors": self.errors
        }

class ExecutionEngine:
    """
    Executes query plans with:
    - Step-by-step execution
    - Error handling
    - Performance monitoring
    - Parallel execution support
    """
    
    def __init__(self):
        """Initialize execution engine."""
        self.execution_contexts: Dict[str, ExecutionContext] = {}
        self.execution_stats = {
            "queries_executed": 0,
            "total_duration_ms": 0.0,
            "total_rows_processed": 0,
            "failed_queries": 0
        }
    
    def execute(self, plan: QueryPlan) -> Dict[str, Any]:
        """
        Execute a query plan.
        
        Args:
            plan: Query execution plan
            
        Returns:
            Execution result with metrics
        """
        context = ExecutionContext(plan.plan_id)
        self.execution_contexts[plan.plan_id] = context
        
        try:
            span = tracer.start_span(f"execute_query:{plan.plan_id}")
            span.add_tag("plan_cost", plan.total_cost)
            span.add_tag("plan_steps", len(plan.steps))
            
            # Execute each step
            intermediate_result = None
            for i, step in enumerate(plan.steps, 1):
                try:
                    step_start = time.time()
                    intermediate_result = self._execute_step(step, intermediate_result, context)
                    step_duration = (time.time() - step_start) * 1000
                    
                    context.execution_stages.append({
                        "step": i,
                        "operation": step.operation.value,
                        "duration_ms": step_duration,
                        "output_rows": step.estimated_output_rows
                    })
                    
                    metrics.record_timer(
                        f"step_{step.operation.value}_duration",
                        step_duration,
                        labels={"plan": plan.plan_id}
                    )
                    
                except Exception as e:
                    error_msg = f"Step {i} ({step.operation.value}) failed: {str(e)}"
                    context.errors.append(error_msg)
                    span.add_tag("step_error", error_msg)
                    logger.error(error_msg)
                    raise
            
            context.finish()
            context.rows_processed = plan.total_estimated_rows
            
            self.execution_stats["queries_executed"] += 1
            self.execution_stats["total_duration_ms"] += context.get_duration_ms()
            self.execution_stats["total_rows_processed"] += context.rows_processed
            
            span.add_tag("status", "success")
            span.add_tag("rows_processed", context.rows_processed)
            tracer.end_span(span)
            
            logger.info(
                f"Query {plan.plan_id} executed in {context.get_duration_ms():.2f}ms "
                f"({context.rows_processed} rows)"
            )
            
            return {
                "success": True,
                "query_id": plan.plan_id,
                "duration_ms": context.get_duration_ms(),
                "rows_processed": context.rows_processed,
                "result": intermediate_result
            }
            
        except Exception as e:
            context.finish()
            self.execution_stats["failed_queries"] += 1
            
            error_msg = f"Query execution failed: {str(e)}"
            logger.error(error_msg)
            
            return {
                "success": False,
                "query_id": plan.plan_id,
                "error": error_msg,
                "duration_ms": context.get_duration_ms()
            }
    
    def _execute_step(self, step, intermediate_result, context) -> Any:
        """Execute a single plan step."""
        if step.operation == PlanOperation.TABLE_SCAN:
            return self._execute_table_scan(step)
        elif step.operation == PlanOperation.INDEX_SCAN:
            return self._execute_index_scan(step)
        elif step.operation == PlanOperation.FILTER:
            return self._execute_filter(step, intermediate_result)
        elif step.operation == PlanOperation.PROJECT:
            return self._execute_project(step, intermediate_result)
        elif step.operation == PlanOperation.JOIN:
            return self._execute_join(step, intermediate_result)
        elif step.operation == PlanOperation.SORT:
            return self._execute_sort(step, intermediate_result)
        elif step.operation == PlanOperation.LIMIT:
            return self._execute_limit(step, intermediate_result)
        else:
            raise ValueError(f"Unknown operation: {step.operation}")
    
    def _execute_table_scan(self, step) -> List[Dict]:
        """Execute table scan."""
        # Mock: return simulated rows
        return [{"id": i, "data": f"row_{i}"} for i in range(100)]
    
    def _execute_index_scan(self, step) -> List[Dict]:
        """Execute index scan."""
        # Mock: return simulated rows
        return [{"id": i, "data": f"indexed_row_{i}"} for i in range(50)]
    
    def _execute_filter(self, step, rows) -> List[Dict]:
        """Apply filter to rows."""
        if not rows:
            return []
        predicates = step.parameters.get("predicates", [])
        # Mock filtering
        return rows[:int(len(rows) * 0.8)]
    
    def _execute_project(self, step, rows) -> List[Dict]:
        """Project columns."""
        if not rows:
            return []
        columns = step.parameters.get("columns", [])
        # Mock projection
        return rows
    
    def _execute_join(self, step, rows) -> List[Dict]:
        """Execute join."""
        if not rows:
            return []
        # Mock join result
        return rows[:int(len(rows) * 0.9)]
    
    def _execute_sort(self, step, rows) -> List[Dict]:
        """Execute sort."""
        if not rows:
            return []
        # Mock sort
        return sorted(rows, key=lambda x: x.get("id", 0), reverse=True)
    
    def _execute_limit(self, step, rows) -> List[Dict]:
        """Apply limit."""
        if not rows:
            return []
        limit = step.parameters.get("limit", 10)
        offset = step.parameters.get("offset", 0)
        return rows[offset:offset + limit]
    
    def get_execution_result(self, query_id: str) -> Optional[Dict[str, Any]]:
        """Get execution result for query."""
        context = self.execution_contexts.get(query_id)
        return context.to_dict() if context else None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        return self.execution_stats

