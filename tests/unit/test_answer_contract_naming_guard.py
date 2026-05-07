from types import SimpleNamespace

from homllm.intelligence.answer_contracts import build_answer_shape_contract


def _coverage(coverage_ratio: float = 1.0, unresolved_claim_ids=()):
    return SimpleNamespace(coverage_ratio=coverage_ratio, unresolved_claim_ids=tuple(unresolved_claim_ids))


def _context(blocks=()):
    return SimpleNamespace(blocks=tuple(blocks))


def test_answer_contract_always_includes_evidence_anchor_rule():
    contract = build_answer_shape_contract(
        query="What are the job lifecycle states?",
        context_artifact=_context(),
        coverage_report=_coverage(),
        claim_packet=None,
    )

    assert contract.active is True
    assert "EVIDENCE ANCHOR RULE" in contract.enforcement_prompt
    assert "Do not infer sibling decorators" in contract.enforcement_prompt


def test_absent_code_mode_keeps_global_evidence_anchor_rule():
    contract = build_answer_shape_contract(
        query="How does the system perform FAISS indexing safely?",
        context_artifact=_context(),
        coverage_report=_coverage(coverage_ratio=0.0, unresolved_claim_ids=("c1",)),
        claim_packet=None,
    )

    assert "EVIDENCE ANCHOR RULE" in contract.enforcement_prompt
    assert contract.query_class == "default"


def test_absent_code_mode_activates_for_how_should_without_identifier_evidence():
    contract = build_answer_shape_contract(
        query="How should an embedding pipeline detect embedding dimension, handle mismatched dimensions, and create a FAISS index safely?",
        context_artifact=_context(
            blocks=(
                SimpleNamespace(
                    file="search_engine/indexer.py",
                    symbol_name="DocumentIndexer",
                    symbol_id="DocumentIndexer",
                    content="embedding dimension validation and generate_embedding implementation",
                ),
            )
        ),
        coverage_report=_coverage(coverage_ratio=0.0, unresolved_claim_ids=("c1",)),
        claim_packet=None,
    )

    assert contract.absent_code_mode is True
    assert "General Guidance" not in contract.enforcement_prompt
    assert "Design Note" not in contract.enforcement_prompt
    assert "## Evidence-Backed Finding" in contract.structure_prompt
    assert "## Repo Gap" in contract.structure_prompt


def test_absent_code_mode_activates_for_missing_fallback_chain():
    contract = build_answer_shape_contract(
        query="Describe the fallback chain when semantic search returns insufficient results.",
        context_artifact=_context(
            blocks=(
                SimpleNamespace(
                    file="api/routes.py",
                    symbol_name="search_endpoint",
                    symbol_id="search_endpoint",
                    content="semantic ranking and permission filter only",
                ),
            )
        ),
        coverage_report=_coverage(coverage_ratio=0.2, unresolved_claim_ids=("c1",)),
        claim_packet=None,
    )

    assert contract.absent_code_mode is True


def test_exact_code_claim_guard_present_without_absent_code_mode():
    contract = build_answer_shape_contract(
        query="Trace the flow through the endpoint",
        context_artifact=_context(
            blocks=(
                SimpleNamespace(
                    file="api/routes.py",
                    symbol_name="endpoint",
                    symbol_id="endpoint",
                    content="@require_auth\n@require_admin\ndef endpoint(...): ...",
                ),
            )
        ),
        coverage_report=_coverage(),
        claim_packet=None,
    )

    assert contract.absent_code_mode is False
    assert "Do not add file/symbol references or line-specific claims" in contract.enforcement_prompt


def test_stress_outcome_query_requires_synthesis_not_catalog():
    contract = build_answer_shape_contract(
        query=(
            "Summarize expected outcomes of a stress test with 100 concurrent requests "
            "(errors, pool saturation, cache distribution, fallbacks, latency percentiles)."
        ),
        context_artifact=_context(
            blocks=(
                SimpleNamespace(
                    file="database/connection.py",
                    symbol_name="ConnectionPool.acquire",
                    symbol_id="ConnectionPool.acquire",
                    content="max_connections active PoolExhaustedError",
                ),
                SimpleNamespace(
                    file="cache/cache_manager.py",
                    symbol_name="CacheManager.get_stats",
                    symbol_id="CacheManager.get_stats",
                    content="memory_hits memory_misses redis_hits redis_misses evictions hit_rate",
                ),
                SimpleNamespace(
                    file="monitoring/metrics.py",
                    symbol_name="MetricsCollector.get_timer_stats",
                    symbol_id="MetricsCollector.get_timer_stats",
                    content="p50_ms p95_ms p99_ms duration timers",
                ),
            )
        ),
        coverage_report=_coverage(),
        claim_packet=None,
    )

    assert "OUTCOME SYNTHESIS CONTRACT" in contract.enforcement_prompt
    assert "project the expected outcome" in contract.enforcement_prompt
    assert "Do not answer as a component catalog" in contract.enforcement_prompt
    assert "Start the Expected Outcomes section with synthesized consequences" in contract.enforcement_prompt
    assert "## Expected Outcomes" in contract.structure_prompt


def test_interaction_query_requires_evidence_limited_integration_statement():
    contract = build_answer_shape_contract(
        query="How do all 5 optimizer rules combine with execution timing and plan caching in complex queries?",
        context_artifact=_context(
            blocks=(
                SimpleNamespace(
                    file="optimization/query_optimizer.py",
                    symbol_name="QueryOptimizer.optimize",
                    symbol_id="QueryOptimizer.optimize",
                    content="Apply optimization rules in sequence estimated_cost optimization_time_ms",
                ),
                SimpleNamespace(
                    file="optimization/query_planner.py",
                    symbol_name="QueryPlanner.plan_query",
                    symbol_id="QueryPlanner.plan_query",
                    content="plan_cache cache_hits cache_misses Generate new plan",
                ),
                SimpleNamespace(
                    file="optimization/execution_engine.py",
                    symbol_name="ExecutionEngine.execute",
                    symbol_id="ExecutionEngine.execute",
                    content="Execute each step duration_ms metrics.record_timer",
                ),
            )
        ),
        coverage_report=_coverage(),
        claim_packet=None,
    )

    assert "INTEGRATION EVIDENCE RULE" in contract.enforcement_prompt
    assert "If the context shows separate components but no caller wiring" in contract.enforcement_prompt
    assert "Do not use words like implicit" in contract.enforcement_prompt
    assert "Do not include example flows that wire separate components together" in contract.enforcement_prompt
    assert "## Evidence-Limited Integration" in contract.structure_prompt
