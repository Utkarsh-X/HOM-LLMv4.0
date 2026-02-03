"""
Unit tests for Action & Remediation Layer (Problem‑2 spec §3–§9).

Verifies: adapter (P1→P2 input), deterministic action matrix, ordering,
one-action-per-axis, fragility handling, ALIGNED→no action, observability contract.
"""

from __future__ import annotations

import pytest

from homllm.remediation import (
    run_remediation,
    run_remediation_from_sufficiency,
    sufficiency_to_remediation_input,
)
from homllm.remediation.interfaces import (
    RemediationInput,
    RemediationResult,
)
from homllm.remediation.matrix import (
    action_for_fragility,
    allowed_action_for_deciding_factor,
    sort_actions_by_priority,
)
from homllm.sufficiency.interfaces import (
    SignalResult,
    SufficiencyResult,
)


def _sufficiency_result(
    final_verdict: str = "SUFFICIENT",
    deciding_factor: str | None = None,
    intent: str = "ARCHITECTURAL",
    semantic_label: str = "SUFFICIENT",
    rule_label: str = "SUFFICIENT",
    structural_label: str = "SUFFICIENT",
) -> SufficiencyResult:
    return SufficiencyResult(
        final_verdict=final_verdict,
        deciding_factor=deciding_factor,
        intent=intent,
        signals={
            "semantic": SignalResult(0.9, semantic_label),
            "rule": SignalResult(0.9, rule_label),
            "structural": SignalResult(0.9, structural_label),
        },
    )


# --- Adapter: P1 → P2 input ---


def test_adapter_aligned_no_failed_axes():
    r = _sufficiency_result(final_verdict="SUFFICIENT", deciding_factor=None)
    inp = sufficiency_to_remediation_input(r)
    assert inp.final_label == "ALIGNED"
    assert inp.deciding_factor is None
    assert inp.failed_axes == ()


def test_adapter_partially_aligned_semantic_failed():
    r = _sufficiency_result(
        final_verdict="PROBABLY_SUFFICIENT",
        deciding_factor="SEMANTIC",
        semantic_label="INSUFFICIENT",
    )
    inp = sufficiency_to_remediation_input(r)
    assert inp.final_label == "PARTIALLY_ALIGNED"
    assert inp.deciding_factor == "SEMANTIC"
    assert "SEMANTIC" in inp.failed_axes


def test_adapter_misaligned_structural_failed():
    r = _sufficiency_result(
        final_verdict="INSUFFICIENT",
        deciding_factor="STRUCTURAL",
        structural_label="INSUFFICIENT",
    )
    inp = sufficiency_to_remediation_input(r)
    assert inp.final_label == "MISALIGNED"
    assert inp.deciding_factor == "STRUCTURAL"
    assert "STRUCTURAL" in inp.failed_axes


def test_adapter_fragility_flag_passed():
    r = _sufficiency_result(final_verdict="SUFFICIENT")
    inp = sufficiency_to_remediation_input(r, fragility_flag=True)
    assert inp.fragility_flag is True


# --- Action matrix: deciding factor → allowed action ---


def test_matrix_structural_retrieval_expansion():
    a = allowed_action_for_deciding_factor("STRUCTURAL")
    assert a is not None
    assert a.action_type == "RETRIEVAL_EXPANSION"
    assert a.trigger_signal == "STRUCTURAL"
    assert "Expand" in a.expected_effect or "retrieval" in a.expected_effect.lower()


def test_matrix_rule_retrieval_re_target():
    a = allowed_action_for_deciding_factor("RULE")
    assert a is not None
    assert a.action_type == "RETRIEVAL_RE_TARGET"
    assert a.trigger_signal == "RULE"


def test_matrix_semantic_token_budget():
    a = allowed_action_for_deciding_factor("SEMANTIC")
    assert a is not None
    assert a.action_type == "TOKEN_BUDGET_INCREASE"
    assert a.trigger_signal == "SEMANTIC"


def test_matrix_fragility_retry_escalation():
    a = action_for_fragility()
    assert a.action_type == "RETRY_ESCALATION"
    assert a.trigger_signal == "HISTORICAL_FRAGILITY"


def test_matrix_ordering_structural_before_token():
    from homllm.remediation.interfaces import RemediationAction

    structural = allowed_action_for_deciding_factor("STRUCTURAL")
    semantic = allowed_action_for_deciding_factor("SEMANTIC")
    assert structural is not None and semantic is not None
    ordered = sort_actions_by_priority([semantic, structural])
    assert ordered[0].action_type == "RETRIEVAL_EXPANSION"
    assert ordered[1].action_type == "TOKEN_BUDGET_INCREASE"


# --- Pipeline: ALIGNED → no action ---


def test_pipeline_aligned_no_actions():
    inp = RemediationInput(
        final_label="ALIGNED",
        deciding_factor=None,
        intent_class="ARCHITECTURAL",
        failed_axes=(),
    )
    out = run_remediation(inp)
    assert out.actions == ()
    assert out.trigger_to_actions == ()


# --- Pipeline: one action per failed axis, ordered ---


def test_pipeline_structural_failure_returns_retrieval_expansion():
    inp = RemediationInput(
        final_label="MISALIGNED",
        deciding_factor="STRUCTURAL",
        intent_class="ARCHITECTURAL",
        failed_axes=("STRUCTURAL",),
    )
    out = run_remediation(inp)
    assert len(out.actions) == 1
    assert out.actions[0].action_type == "RETRIEVAL_EXPANSION"
    assert out.actions[0].trigger_signal == "STRUCTURAL"
    assert len(out.trigger_to_actions) == 1


def test_pipeline_fragility_adds_retry_escalation():
    inp = RemediationInput(
        final_label="PARTIALLY_ALIGNED",
        deciding_factor="SEMANTIC",
        intent_class="BEHAVIORAL",
        failed_axes=("SEMANTIC",),
        fragility_flag=True,
    )
    out = run_remediation(inp)
    action_types = [a.action_type for a in out.actions]
    assert "TOKEN_BUDGET_INCREASE" in action_types
    assert "RETRY_ESCALATION" in action_types
    assert out.actions[-1].action_type == "RETRY_ESCALATION"  # last per ordering


def test_pipeline_one_action_per_axis_no_duplicate_axis():
    inp = RemediationInput(
        final_label="MISALIGNED",
        deciding_factor="STRUCTURAL",
        intent_class="ARCHITECTURAL",
        failed_axes=("STRUCTURAL", "STRUCTURAL"),  # duplicate
    )
    out = run_remediation(inp)
    assert len(out.actions) == 1


def test_pipeline_multiple_axes_ordered_structural_first():
    inp = RemediationInput(
        final_label="MISALIGNED",
        deciding_factor="STRUCTURAL",
        intent_class="ARCHITECTURAL",
        failed_axes=("SEMANTIC", "STRUCTURAL"),
    )
    out = run_remediation(inp)
    assert len(out.actions) == 2
    assert out.actions[0].action_type == "RETRIEVAL_EXPANSION"
    assert out.actions[1].action_type == "TOKEN_BUDGET_INCREASE"


# --- Observability: to_dict ---


def test_result_to_dict_contract():
    inp = RemediationInput(
        final_label="MISALIGNED",
        deciding_factor="STRUCTURAL",
        intent_class="ARCHITECTURAL",
        failed_axes=("STRUCTURAL",),
    )
    out = run_remediation(inp)
    d = out.to_dict()
    assert "actions" in d
    assert len(d["actions"]) == 1
    assert d["actions"][0]["action_type"] == "RETRIEVAL_EXPANSION"
    assert d["actions"][0]["trigger_signal"] == "STRUCTURAL"
    assert "expected_effect" in d["actions"][0]
    assert d["actions"][0]["actual_outcome"] is None
    assert "trigger_to_actions" in d


# --- End-to-end: from SufficiencyResult ---


def test_run_remediation_from_sufficiency_aligned_empty():
    r = _sufficiency_result(final_verdict="SUFFICIENT")
    out = run_remediation_from_sufficiency(r)
    assert isinstance(out, RemediationResult)
    assert out.actions == ()


def test_run_remediation_from_sufficiency_misaligned_structural():
    r = _sufficiency_result(
        final_verdict="INSUFFICIENT",
        deciding_factor="STRUCTURAL",
        structural_label="INSUFFICIENT",
    )
    out = run_remediation_from_sufficiency(r)
    assert len(out.actions) == 1
    assert out.actions[0].action_type == "RETRIEVAL_EXPANSION"


def test_run_remediation_from_sufficiency_with_fragility():
    r = _sufficiency_result(
        final_verdict="INSUFFICIENT",
        deciding_factor="RULE",
        rule_label="INSUFFICIENT",
    )
    out = run_remediation_from_sufficiency(r, fragility_flag=True)
    action_types = [a.action_type for a in out.actions]
    assert "RETRIEVAL_RE_TARGET" in action_types
    assert "RETRY_ESCALATION" in action_types


# --- Must not infer: unknown axis → no action ---


def test_unknown_axis_ignored_no_action():
    inp = RemediationInput(
        final_label="MISALIGNED",
        deciding_factor="STRUCTURAL",
        intent_class="ARCHITECTURAL",
        failed_axes=("UNKNOWN_AXIS",),  # not in contract
    )
    out = run_remediation(inp)
    # UNKNOWN_AXIS has no mapping; only deciding_factor could drive action but we iterate failed_axes
    # failed_axes contains UNKNOWN_AXIS which _as_deciding_factor returns None for → no action
    assert len(out.actions) == 0
