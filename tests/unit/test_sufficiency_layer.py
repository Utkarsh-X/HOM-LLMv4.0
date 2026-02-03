"""
Unit tests for Intent-Gated Sufficiency Layer (plan §1–§7).

Verifies: intent gating, veto logic (conjunctive), structural authority,
output contract (deciding_factor, signals), read-only safety.
"""

from __future__ import annotations

import pytest

from homllm.context.interfaces import ContextArtifact, ContextBlock
from homllm.sufficiency import run_sufficiency
from homllm.sufficiency.interfaces import SufficiencyResult
from homllm.sufficiency.intent import classify_intent
from homllm.sufficiency.veto import resolve_veto


def _block(
    block_id: str = "b1",
    file: str = "foo.py",
    start_line: int = 1,
    end_line: int = 10,
    content: str = "def foo(): pass",
    symbol_id: str | None = "sym1",
    symbol_name: str | None = "foo",
    provenance: tuple[str, ...] = (),
) -> ContextBlock:
    return ContextBlock(
        block_id=block_id,
        file=file,
        start_line=start_line,
        end_line=end_line,
        content=content,
        symbol_id=symbol_id,
        symbol_name=symbol_name,
        provenance=provenance,
    )


def _artifact(blocks: list[ContextBlock]) -> ContextArtifact:
    text = "\n\n".join(b.content for b in blocks)
    return ContextArtifact(
        query_id="q1",
        context_text=text,
        blocks=tuple(blocks),
        token_budget=3200,
        used_tokens=len(text.split()),
        provenance={},
        explain_trace=(),
    )


# --- Intent gating ---


def test_intent_architectural_mandatory_axes():
    """Mandatory axes change per intent; ARCHITECTURAL has STRUCTURAL, SEMANTIC."""
    r = classify_intent("How do all 5 optimizer rules combine with execution timing?")
    assert r.intent == "ARCHITECTURAL"
    assert "STRUCTURAL" in r.mandatory_axes
    assert "SEMANTIC" in r.mandatory_axes
    assert r.early_exit_allowed is False


def test_intent_behavioral():
    r = classify_intent("How does ConnectionPool behave when all connections are in use?")
    assert r.intent == "BEHAVIORAL"
    assert "RULE" in r.mandatory_axes
    assert "SEMANTIC" in r.mandatory_axes


def test_intent_unknown_conservative():
    r = classify_intent("Something random xyz")
    assert r.intent == "UNKNOWN"
    assert "STRUCTURAL" in r.mandatory_axes
    assert "RULE" in r.mandatory_axes
    assert "SEMANTIC" in r.mandatory_axes
    assert r.early_exit_allowed is False


# --- Veto logic conjunctive ---


def test_veto_one_hard_failure_blocks_sufficient():
    """One hard failure (structural or rule) blocks SUFFICIENT."""
    from homllm.sufficiency.interfaces import IntentResult, SignalResult

    intent = IntentResult(
        intent="ARCHITECTURAL",
        mandatory_axes=("STRUCTURAL", "SEMANTIC"),
        early_exit_allowed=False,
    )
    signals = {
        "semantic": SignalResult(score=0.9, label="SUFFICIENT"),
        "rule": SignalResult(score=0.8, label="SUFFICIENT"),
        "structural": SignalResult(score=0.3, label="INSUFFICIENT"),
    }
    out = resolve_veto(intent, signals)
    assert out.final_verdict == "INSUFFICIENT"
    assert out.deciding_factor == "STRUCTURAL"


def test_veto_no_signal_overrides_hard_veto():
    """Semantic SUFFICIENT cannot override structural INSUFFICIENT."""
    from homllm.sufficiency.interfaces import IntentResult, SignalResult

    intent = IntentResult(
        intent="ARCHITECTURAL",
        mandatory_axes=("STRUCTURAL", "SEMANTIC"),
        early_exit_allowed=False,
    )
    signals = {
        "semantic": SignalResult(score=0.95, label="SUFFICIENT"),
        "rule": SignalResult(score=0.8, label="SUFFICIENT"),
        "structural": SignalResult(score=0.2, label="INSUFFICIENT"),
    }
    out = resolve_veto(intent, signals)
    assert out.final_verdict == "INSUFFICIENT"
    assert out.deciding_factor == "STRUCTURAL"


def test_veto_semantic_soft_only():
    """Semantic insufficiency → PROBABLY_SUFFICIENT, not INSUFFICIENT."""
    from homllm.sufficiency.interfaces import IntentResult, SignalResult

    intent = IntentResult(
        intent="BEHAVIORAL",
        mandatory_axes=("RULE", "SEMANTIC"),
        early_exit_allowed=True,
    )
    signals = {
        "semantic": SignalResult(score=0.4, label="INSUFFICIENT"),
        "rule": SignalResult(score=0.8, label="SUFFICIENT"),
        "structural": SignalResult(score=0.7, label="SUFFICIENT"),
    }
    out = resolve_veto(intent, signals)
    assert out.final_verdict == "PROBABLY_SUFFICIENT"
    assert out.deciding_factor == "SEMANTIC"


def test_veto_all_pass_sufficient():
    from homllm.sufficiency.interfaces import IntentResult, SignalResult

    intent = IntentResult(
        intent="IMPLEMENTATION",
        mandatory_axes=("RULE", "STRUCTURAL", "SEMANTIC"),
        early_exit_allowed=True,
    )
    signals = {
        "semantic": SignalResult(score=0.8, label="SUFFICIENT"),
        "rule": SignalResult(score=0.7, label="SUFFICIENT"),
        "structural": SignalResult(score=0.6, label="SUFFICIENT"),
    }
    out = resolve_veto(intent, signals)
    assert out.final_verdict == "SUFFICIENT"
    assert out.deciding_factor is None


# --- Output contract ---


def test_output_contract_shape():
    """Each signal emits {score, label}; final output includes deciding_factor."""
    art = _artifact([_block(content="CacheManager get set")])
    out = run_sufficiency("What happens when L1 L2 L3 caches miss?", art, embedder=None)
    assert hasattr(out, "final_verdict")
    assert hasattr(out, "deciding_factor")
    assert hasattr(out, "intent")
    assert hasattr(out, "signals")
    assert "semantic" in out.signals
    assert "rule" in out.signals
    assert "structural" in out.signals
    for k, v in out.signals.items():
        assert hasattr(v, "score")
        assert hasattr(v, "label")
        assert v.label in ("SUFFICIENT", "INSUFFICIENT")
    d = out.to_dict()
    assert "final_verdict" in d
    assert "deciding_factor" in d
    assert "signals" in d
    for sig in d["signals"].values():
        assert "score" in sig
        assert "label" in sig


# --- Read-only: no context mutation ---


def test_read_only_no_context_mutation():
    """Pipeline does not modify context_artifact."""
    blocks = [_block(block_id="b1", content="original")]
    art = _artifact(blocks)
    run_sufficiency("query", art, embedder=None)
    assert art.blocks[0].content == "original"
    assert len(art.blocks) == 1


# --- Structural authority (structural insufficient → hard veto when mandatory) ---


def test_structural_insufficiency_hard_veto_when_mandatory():
    """Empty or weak structure + ARCHITECTURAL intent → INSUFFICIENT, deciding_factor STRUCTURAL."""
    empty = _artifact([])
    # Empty context: structural signal will be INSUFFICIENT
    out = run_sufficiency(
        "How do all 5 optimizer rules combine with execution timing?",
        empty,
        embedder=None,
    )
    # Intent is ARCHITECTURAL → STRUCTURAL mandatory; empty blocks → structural fail
    assert out.intent == "ARCHITECTURAL"
    assert out.signals["structural"].label == "INSUFFICIENT"
    assert out.final_verdict == "INSUFFICIENT"
    assert out.deciding_factor == "STRUCTURAL"
