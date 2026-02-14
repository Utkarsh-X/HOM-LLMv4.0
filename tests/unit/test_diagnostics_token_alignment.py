import pytest


def test_l1_diagnostics_token_count_aligns_with_context_used_tokens():
    """
    L1 diagnostics should reflect the context pipeline token accounting.
    This prevents false "low utilization" triggers downstream.
    """
    from homllm.context.interfaces import ContextArtifact, ContextBlock
    from homllm.intelligence.diagnostics_runner import run_diagnostics

    blocks = (
        ContextBlock(
            block_id="b1",
            file="a.py",
            start_line=1,
            end_line=10,
            content="x " * 1000,
            symbol_id=None,
            symbol_name=None,
            provenance=("bm25",),
        ),
        ContextBlock(
            block_id="b2",
            file="b.py",
            start_line=1,
            end_line=10,
            content="y " * 1000,
            symbol_id=None,
            symbol_name=None,
            provenance=("vector",),
        ),
    )

    context = ContextArtifact(
        query_id="q",
        context_text="",
        blocks=blocks,
        token_budget=3200,
        used_tokens=1200,
        provenance={
            "blocks": [
                {"block_id": "b1", "tokens": 700},
                {"block_id": "b2", "tokens": 500},
            ]
        },
        explain_trace=(),
    )

    snap = run_diagnostics(context, force_run=True)
    assert snap is not None
    assert snap.level1.status == "available"
    assert snap.level1.result is not None
    assert snap.level1.result.total_tokens == 1200
    assert len(snap.level1.result.blocks) == 2
    assert {b.block_id: b.tokens for b in snap.level1.result.blocks} == {"b1": 700, "b2": 500}
