"""Hidden FAIL_TO_PASS tests for optimization.query_optimizer.QueryOptimizer.

The agent must make predicate pushdown order filters from most selective
(lowest selectivity value) to least selective.
"""

from optimization.query_optimizer import QueryFilter, QueryOperations, QueryOptimizer


def _equality_filter() -> QueryFilter:
    return QueryFilter(field="id", operator="==", value=42)


def _range_filter() -> QueryFilter:
    return QueryFilter(field="score", operator=">", value=10)


def test_predicate_pushdown_orders_most_selective_first() -> None:
    optimizer = QueryOptimizer(available_indices=["id"])
    operations = QueryOperations(
        filters=[_range_filter(), _equality_filter()],
        projections=["id", "score"],
        joins=[],
    )
    result = optimizer.optimize(operations)
    # Equality (selectivity 0.01) is more selective than range (0.1),
    # so the equality filter must come first after pushdown.
    assert result.optimized.filters[0].operator == "=="


def test_equality_filter_uses_index() -> None:
    optimizer = QueryOptimizer(available_indices=["id"])
    operations = QueryOperations(
        filters=[_equality_filter()],
        projections=["id"],
        joins=[],
    )
    result = optimizer.optimize(operations)
    assert result.index_used == "id"
