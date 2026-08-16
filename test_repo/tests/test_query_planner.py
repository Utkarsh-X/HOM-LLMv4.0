"""Hidden test: the plan cache must distinguish queries by parameters.

QueryPlanner.plan_query builds its cache key from the query text only, so
two calls with the same SQL but different parameters return the same cached
plan. This test asserts parameter-aware planning.
"""
from optimization.query_planner import QueryPlanner


def test_same_query_different_parameters_produce_distinct_plans():
    planner = QueryPlanner()
    query = "SELECT * FROM documents WHERE status = $1 AND owner_id = $2"

    plan_a = planner.plan_query(query, {"status": "active", "owner_id": 1})
    plan_b = planner.plan_query(query, {"status": "active", "owner_id": 2})

    assert plan_a.plan_id != plan_b.plan_id, (
        "plans with different parameters must not share a cached plan"
    )
    stats = planner.get_stats()
    assert stats["cache_hits"] == 0, f"expected no cache hits, got {stats}"


def test_identical_query_and_parameters_are_cached():
    planner = QueryPlanner()
    query = "SELECT * FROM documents WHERE status = $1"

    plan_a = planner.plan_query(query, {"status": "active"})
    plan_b = planner.plan_query(query, {"status": "active"})

    assert plan_a.plan_id == plan_b.plan_id
    stats = planner.get_stats()
    assert stats["cache_hits"] == 1, f"expected one cache hit, got {stats}"
