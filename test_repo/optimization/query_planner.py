"""
Query execution planning.
Generates execution plans and manages plan caching.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class PlanOperation(Enum):
    """Query plan operations."""
    TABLE_SCAN = "table_scan"
    INDEX_SCAN = "index_scan"
    FILTER = "filter"
    PROJECT = "project"
    JOIN = "join"
    SORT = "sort"
    LIMIT = "limit"

@dataclass
class PlanStep:
    """Single step in a query plan."""
    operation: PlanOperation
    parameters: Dict[str, Any]
    estimated_output_rows: int
    estimated_cost: float
    parallelizable: bool = False

class QueryPlan:
    """
    Represents a query execution plan.
    Contains ordered steps for execution.
    """
    
    def __init__(self, plan_id: str, steps: List[PlanStep]):
        """
        Initialize query plan.
        
        Args:
            plan_id: Unique plan ID
            steps: Execution steps
        """
        self.plan_id = plan_id
        self.steps = steps
        self.total_cost = sum(step.estimated_cost for step in steps)
        self.total_estimated_rows = steps[-1].estimated_output_rows if steps else 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert plan to dictionary."""
        return {
            "plan_id": self.plan_id,
            "total_cost": self.total_cost,
            "estimated_rows": self.total_estimated_rows,
            "step_count": len(self.steps),
            "steps": [
                {
                    "operation": step.operation.value,
                    "parameters": step.parameters,
                    "estimated_cost": step.estimated_cost,
                    "estimated_output_rows": step.estimated_output_rows
                }
                for step in self.steps
            ]
        }
    
    def explain(self) -> str:
        """Generate human-readable plan explanation."""
        lines = [f"Query Plan {self.plan_id}:"]
        lines.append(f"  Total Cost: {self.total_cost:.2f}")
        lines.append(f"  Estimated Rows: {self.total_estimated_rows}")
        lines.append("  Steps:")
        
        for i, step in enumerate(self.steps, 1):
            indent = "    " if i == 1 else "    -> "
            lines.append(
                f"{indent}{i}. {step.operation.value} "
                f"(cost: {step.estimated_cost:.2f}, rows: {step.estimated_output_rows})"
            )
            for k, v in step.parameters.items():
                lines.append(f"       {k}: {v}")
        
        return "\n".join(lines)

class QueryPlanner:
    """
    Generates query execution plans.
    Caches and reuses plans for similar queries.
    """
    
    def __init__(self, enable_caching: bool = True):
        """Initialize query planner."""
        self.enable_caching = enable_caching
        self.plan_cache: Dict[str, QueryPlan] = {}
        self.plan_stats = {
            "plans_generated": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }
    
    def plan_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> QueryPlan:
        """
        Generate execution plan for query.
        
        Args:
            query: Query string
            parameters: Query parameters
            
        Returns:
            Query execution plan
        """
        # Generate cache key
        cache_key = self._make_cache_key(query)
        
        # Check cache
        if self.enable_caching and cache_key in self.plan_cache:
            self.plan_stats["cache_hits"] += 1
            logger.debug(f"Cache hit for query plan: {cache_key}")
            return self.plan_cache[cache_key]
        
        self.plan_stats["cache_misses"] += 1
        
        # Generate new plan
        steps = self._generate_plan_steps(query)
        plan = QueryPlan(cache_key, steps)
        
        if self.enable_caching:
            self.plan_cache[cache_key] = plan
        
        self.plan_stats["plans_generated"] += 1
        logger.info(f"Generated query plan with {len(steps)} steps")
        
        return plan
    
    def _generate_plan_steps(self, query: str) -> List[PlanStep]:
        """Generate execution plan steps from query."""
        steps = []
        
        # Parse query (mock)
        has_scan = "SELECT" in query
        has_filter = "WHERE" in query
        has_sort = "ORDER BY" in query
        has_limit = "LIMIT" in query
        has_join = "JOIN" in query
        
        # 1. Initial scan
        if has_scan:
            steps.append(PlanStep(
                operation=PlanOperation.TABLE_SCAN,
                parameters={"table": "documents"},
                estimated_output_rows=10000,
                estimated_cost=1000.0
            ))
        
        # 2. Join if needed
        if has_join:
            steps.append(PlanStep(
                operation=PlanOperation.JOIN,
                parameters={"join_type": "inner", "condition": "id = document_id"},
                estimated_output_rows=8000,
                estimated_cost=500.0
            ))
        
        # 3. Filter
        if has_filter:
            steps.append(PlanStep(
                operation=PlanOperation.FILTER,
                parameters={"predicates": ["status = active"]},
                estimated_output_rows=4000,
                estimated_cost=100.0
            ))
        
        # 4. Project
        steps.append(PlanStep(
            operation=PlanOperation.PROJECT,
            parameters={"columns": ["id", "title", "content"]},
            estimated_output_rows=4000,
            estimated_cost=50.0
        ))
        
        # 5. Sort
        if has_sort:
            steps.append(PlanStep(
                operation=PlanOperation.SORT,
                parameters={"sort_key": "created_at", "order": "DESC"},
                estimated_output_rows=4000,
                estimated_cost=300.0
            ))
        
        # 6. Limit
        if has_limit:
            steps.append(PlanStep(
                operation=PlanOperation.LIMIT,
                parameters={"limit": 100, "offset": 0},
                estimated_output_rows=100,
                estimated_cost=10.0
            ))
        
        return steps
    
    def _make_cache_key(self, query: str) -> str:
        """Generate cache key for query."""
        import hashlib
        return hashlib.md5(query.encode()).hexdigest()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get planner statistics."""
        total = self.plan_stats["cache_hits"] + self.plan_stats["cache_misses"]
        hit_rate = (self.plan_stats["cache_hits"] / total * 100) if total > 0 else 0
        
        return {
            "plans_generated": self.plan_stats["plans_generated"],
            "cache_size": len(self.plan_cache),
            "cache_hits": self.plan_stats["cache_hits"],
            "cache_misses": self.plan_stats["cache_misses"],
            "hit_rate": f"{hit_rate:.2f}%"
        }

