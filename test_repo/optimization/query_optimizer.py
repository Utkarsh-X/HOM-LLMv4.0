"""
Query optimizer with rule-based and cost-based optimization.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class OptimizationRule(Enum):
    """Query optimization rules."""
    PREDICATE_PUSHDOWN = "predicate_pushdown"
    PROJECTION_PUSHDOWN = "projection_pushdown"
    CONSTANT_FOLDING = "constant_folding"
    DEAD_CODE_ELIMINATION = "dead_code_elimination"
    COMMON_SUBEXPRESSION_ELIMINATION = "common_subexpression_elimination"
    JOIN_REORDERING = "join_reordering"
    INDEX_SELECTION = "index_selection"

@dataclass
class QueryFilter:
    """Represents a query filter condition."""
    field: str
    operator: str  # ==, !=, <, >, <=, >=, IN, LIKE
    value: Any
    
    def can_use_index(self, available_indices: List[str]) -> bool:
        """Check if this filter can use an index."""
        return self.field in available_indices

@dataclass
class QueryOperations:
    """Query operations to optimize."""
    filters: List[QueryFilter]
    projections: List[str]
    joins: List[Dict[str, Any]]
    sorting: Optional[Dict[str, str]] = None
    limit: Optional[int] = None
    offset: Optional[int] = None

class QueryOptimizer:
    """
    Query optimizer with multiple optimization strategies:
    - Rule-based optimization
    - Cost estimation
    - Plan comparison
    - Execution statistics collection
    """
    
    def __init__(self, available_indices: Optional[List[str]] = None):
        """
        Initialize optimizer.
        
        Args:
            available_indices: List of available database indices
        """
        self.available_indices = available_indices or []
        self.optimization_stats = {
            "total_queries": 0,
            "optimized_queries": 0,
            "optimization_time_ms": 0.0
        }
    
    def optimize(self, operations: QueryOperations) -> 'OptimizedQuery':
        """
        Optimize a query.
        
        Args:
            operations: Query operations to optimize
            
        Returns:
            Optimized query plan
        """
        import time
        start_time = time.time()
        
        self.optimization_stats["total_queries"] += 1
        
        # Apply optimization rules in sequence
        optimized = operations
        
        # Rule 1: Predicate pushdown - filter as early as possible
        optimized = self._apply_predicate_pushdown(optimized)
        
        # Rule 2: Projection pushdown - select only needed columns
        optimized = self._apply_projection_pushdown(optimized)
        
        # Rule 3: Constant folding
        optimized = self._apply_constant_folding(optimized)
        
        # Rule 4: Index selection
        index_used = self._apply_index_selection(optimized)
        
        # Rule 5: Join reordering
        if optimized.joins:
            optimized = self._apply_join_reordering(optimized)
        
        # Estimate cost
        estimated_cost = self._estimate_cost(optimized)
        
        optimization_time = (time.time() - start_time) * 1000
        self.optimization_stats["optimization_time_ms"] += optimization_time
        
        if estimated_cost < float('inf'):
            self.optimization_stats["optimized_queries"] += 1
        
        return OptimizedQuery(
            original=operations,
            optimized=optimized,
            estimated_cost=estimated_cost,
            index_used=index_used,
            optimization_time_ms=optimization_time
        )
    
    def _apply_predicate_pushdown(self, ops: QueryOperations) -> QueryOperations:
        """Move filters as early as possible."""
        # Reorder filters by selectivity (most selective first)
        ops.filters.sort(
            key=lambda f: self._estimate_selectivity(f),
            reverse=True
        )
        logger.debug("Applied predicate pushdown optimization")
        return ops
    
    def _apply_projection_pushdown(self, ops: QueryOperations) -> QueryOperations:
        """Remove unnecessary columns."""
        # Keep only projections and columns used in filters/joins
        necessary_columns = set(ops.projections)
        for f in ops.filters:
            necessary_columns.add(f.field)
        for join in ops.joins:
            necessary_columns.add(join.get("on_field", ""))
        
        ops.projections = list(necessary_columns)
        logger.debug(f"Applied projection pushdown: {len(ops.projections)} columns")
        return ops
    
    def _apply_constant_folding(self, ops: QueryOperations) -> QueryOperations:
        """Evaluate constant expressions."""
        # Evaluate filters with constant values
        simplified_filters = []
        for f in ops.filters:
            if self._is_constant_expression(f):
                if self._evaluate_constant(f):
                    simplified_filters.append(f)
            else:
                simplified_filters.append(f)
        
        ops.filters = simplified_filters
        logger.debug("Applied constant folding optimization")
        return ops
    
    def _apply_index_selection(self, ops: QueryOperations) -> Optional[str]:
        """Select best index for the query."""
        best_index = None
        best_score = 0.0
        
        for idx in self.available_indices:
            score = 0.0
            for f in ops.filters:
                if f.field == idx:
                    score += self._get_index_benefit(f)
            
            if score > best_score:
                best_score = score
                best_index = idx
        
        if best_index:
            logger.debug(f"Selected index: {best_index} (score: {best_score:.2f})")
        
        return best_index
    
    def _apply_join_reordering(self, ops: QueryOperations) -> QueryOperations:
        """Reorder joins by cost."""
        if len(ops.joins) <= 1:
            return ops
        
        # Sort joins by estimated join cost
        ops.joins.sort(key=lambda j: self._estimate_join_cost(j))
        logger.debug("Applied join reordering optimization")
        return ops
    
    def _estimate_cost(self, ops: QueryOperations) -> float:
        """Estimate query execution cost."""
        cost = 0.0
        
        # Cost for scanning with filters
        for f in ops.filters:
            if f.can_use_index(self.available_indices):
                cost += 100.0  # Index scan cost
            else:
                cost += 1000.0  # Full table scan cost
        
        # Cost for joins
        for join in ops.joins:
            cost += 500.0
        
        # Cost for sorting
        if ops.sorting:
            cost += 300.0
        
        return cost
    
    def _estimate_selectivity(self, f: QueryFilter) -> float:
        """Estimate filter selectivity (0-1)."""
        # Mock estimation based on operator
        if f.operator == "==":
            return 0.01
        elif f.operator in ["<", ">"]:
            return 0.1
        elif f.operator == "IN":
            return 0.05
        else:
            return 0.2
    
    def _get_index_benefit(self, f: QueryFilter) -> float:
        """Estimate index benefit for filter."""
        if f.operator == "==":
            return 100.0
        elif f.operator in ["<", ">"]:
            return 50.0
        else:
            return 10.0
    
    def _estimate_join_cost(self, join: Dict[str, Any]) -> float:
        """Estimate cost of a join."""
        rows = join.get("estimated_rows", 1000)
        return float(rows)
    
    def _is_constant_expression(self, f: QueryFilter) -> bool:
        """Check if filter is a constant expression."""
        return isinstance(f.value, (int, float, str, bool))
    
    def _evaluate_constant(self, f: QueryFilter) -> bool:
        """Evaluate constant expression."""
        try:
            if f.operator == "==":
                return f.value is not None
            elif f.operator == "<":
                return f.value < 0
            else:
                return True
        except:
            return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get optimization statistics."""
        return self.optimization_stats

@dataclass
class OptimizedQuery:
    """Result of query optimization."""
    original: QueryOperations
    optimized: QueryOperations
    estimated_cost: float
    index_used: Optional[str] = None
    optimization_time_ms: float = 0.0
    
    def improvement_ratio(self) -> float:
        """Estimate query improvement ratio."""
        if self.estimated_cost == 0:
            return 1.0
        # Mock calculation
        return 1.2

