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
    assert "## Repo Finding" in contract.structure_prompt


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
