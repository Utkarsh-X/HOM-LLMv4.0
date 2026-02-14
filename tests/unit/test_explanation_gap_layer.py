"""
Unit tests for Structural Explanation Gap Detection (Problem 4 spec).

Covers: escalation only upward, rules dominate, ambiguity never SHALLOW_OK,
cold-start, rule triggers (example/detailed/debug), history escalation,
auditability, no mutation. Read-only diagnostic only.
"""

from __future__ import annotations

import pytest

from homllm.explanation_gap import run_explanation_gap
from homllm.explanation_gap.constants import (
    INTENT_DEFAULT,
    INTENT_TABLE_VERSION,
)
from homllm.explanation_gap.history import historical_depth_escalation
from homllm.explanation_gap.interfaces import (
    HistoryDepthStats,
    max_severity,
    severity_rank,
)
from homllm.explanation_gap.rules import classify_depth_intent, rule_based_depth


# --- Severity: escalation only upward ---


def test_severity_order_example_recommended_highest():
    assert severity_rank("EXAMPLE_RECOMMENDED") < severity_rank("DETAILED_REQUIRED")
    assert severity_rank("DETAILED_REQUIRED") < severity_rank("SHALLOW_OK")


def test_max_severity_never_downgrades():
    assert max_severity("SHALLOW_OK", "DETAILED_REQUIRED") == "DETAILED_REQUIRED"
    assert max_severity("DETAILED_REQUIRED", "SHALLOW_OK") == "DETAILED_REQUIRED"
    assert max_severity("EXAMPLE_RECOMMENDED", "DETAILED_REQUIRED") == "EXAMPLE_RECOMMENDED"
    assert max_severity("SHALLOW_OK", "EXAMPLE_RECOMMENDED") == "EXAMPLE_RECOMMENDED"


# --- Intent-to-depth table (versioned) ---


def test_intent_table_versioned():
    assert INTENT_TABLE_VERSION == "1.0"


def test_intent_defaults():
    assert INTENT_DEFAULT["FACTUAL"] == "SHALLOW_OK"
    assert INTENT_DEFAULT["EXPLANATORY"] == "DETAILED_REQUIRED"
    assert INTENT_DEFAULT["DEBUGGING"] == "DETAILED_REQUIRED"
    assert INTENT_DEFAULT["ILLUSTRATIVE"] == "EXAMPLE_RECOMMENDED"


# --- Rule-based: example / detailed / debug ---


def test_rule_example_recommended():
    label, trigger, _ = rule_based_depth("Show me an example of how to use the API")
    assert label == "EXAMPLE_RECOMMENDED"
    assert "Rule" in trigger or "EXAMPLE" in trigger


def test_rule_detailed_required_why():
    label, trigger, _ = rule_based_depth("Why does this function fail?")
    assert label == "DETAILED_REQUIRED"
    assert "Rule" in trigger or "IntentDefault" in trigger


def test_rule_detailed_required_how():
    label, _, _ = rule_based_depth("How does the execution flow work?")
    assert label == "DETAILED_REQUIRED"


def test_rule_debug_markers():
    label, _, _ = rule_based_depth("What happens when we hit an error in production?")
    assert label == "DETAILED_REQUIRED"


def test_rule_factual_shallow_ok():
    label, trigger, _ = rule_based_depth("What is the name of the main module?")
    assert label == "SHALLOW_OK"
    assert "IntentDefault" in trigger or "FACTUAL" in trigger


def test_classify_depth_intent():
    assert classify_depth_intent("show me an example") == "ILLUSTRATIVE"
    assert classify_depth_intent("why does it fail") == "EXPLANATORY"
    assert classify_depth_intent("error when loading") == "DEBUGGING"
    assert classify_depth_intent("what is X") == "FACTUAL"
    assert (
        classify_depth_intent(
            "How do all 5 optimizer rules combine with execution timing and plan caching?"
        )
        == "EXPLANATORY"
    )
    assert (
        classify_depth_intent(
            "Trace the execution flow when an admin user calls the admin_search_endpoint through all layers."
        )
        == "EXPLANATORY"
    )


# --- History: escalation only; cold-start ---


def test_historical_cold_start_no_downgrade():
    label, trigger, _ = historical_depth_escalation("DETAILED_REQUIRED", None)
    assert label == "DETAILED_REQUIRED"
    assert "cold_start" in trigger or "insufficient" in trigger.lower()


def test_historical_escalation_when_high_pct():
    stats = HistoryDepthStats(runs_in_bucket=10, pct_expanded_or_manual=0.5, pct_shallow_complaints=0.1)
    label, _, _ = historical_depth_escalation("SHALLOW_OK", stats)
    assert label == "DETAILED_REQUIRED"


def test_historical_never_downgrade():
    stats = HistoryDepthStats(runs_in_bucket=10, pct_expanded_or_manual=0.0, pct_shallow_complaints=0.0)
    label, _, _ = historical_depth_escalation("EXAMPLE_RECOMMENDED", stats)
    assert label == "EXAMPLE_RECOMMENDED"


# --- Pipeline: output contract, auditability ---


def test_pipeline_exactly_one_label():
    out = run_explanation_gap("What is X?")
    assert out.label in ("SHALLOW_OK", "DETAILED_REQUIRED", "EXAMPLE_RECOMMENDED")


def test_pipeline_auditability_fields():
    out = run_explanation_gap("Why does this fail?")
    assert out.deciding_trigger
    assert out.confidence >= 0 and out.confidence <= 1
    assert out.evidence_volume >= 0
    assert out.rationale
    assert len(out.per_signal_outputs) >= 1


def test_pipeline_to_dict():
    out = run_explanation_gap("Show me an example")
    d = out.to_dict()
    assert d["label"] == out.label
    assert "deciding_trigger" in d
    assert "confidence" in d
    assert "evidence_volume" in d
    assert "per_signal_outputs" in d


def test_pipeline_cold_start_low_evidence():
    out = run_explanation_gap("What is Y?", history_stats=None)
    assert out.evidence_volume == 0
    assert out.cold_start is True
    assert out.confidence <= 0.6  # medium, bounded


# --- Escalation only: rules dominate ---


def test_example_beats_detailed():
    out = run_explanation_gap("Show me an example of why this fails")
    assert out.label == "EXAMPLE_RECOMMENDED"


def test_ambiguity_never_shallow_when_rules_fire():
    out = run_explanation_gap("Explain how it works with an example")
    assert out.label in ("DETAILED_REQUIRED", "EXAMPLE_RECOMMENDED")


# --- No mutation: deterministic ---


def test_deterministic_same_input():
    out1 = run_explanation_gap("Why does X happen?")
    out2 = run_explanation_gap("Why does X happen?")
    assert out1.label == out2.label
    assert out1.deciding_trigger == out2.deciding_trigger
