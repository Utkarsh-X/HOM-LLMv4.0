"""
Stage 3 — Optional precision upgrade (spec §4.3, §5).

Lightweight classifier may only upgrade; never downgrade.
Ambiguity must never yield SHALLOW_OK. Without a real offline model, this is a no-op
or rule-based upgrade-only pass.
"""

from __future__ import annotations

from homllm.explanation_gap.interfaces import (
    DepthLabelType,
    SignalOutput,
    max_severity,
)


def classifier_upgrade_only(
    current_label: DepthLabelType,
    query: str,
) -> tuple[DepthLabelType, str, list[SignalOutput]]:
    """
    Stage 3: only upgrade. Never downgrade from rule-triggered or embedding result.
    Stub: no real classifier; returns current_label unchanged.
    Future: offline DeBERTa-small or similar may upgrade SHALLOW_OK → DETAILED_REQUIRED
    when implicit depth detected, or DETAILED_REQUIRED → EXAMPLE_RECOMMENDED when
    illustrative cues present.
    """
    sig = SignalOutput(
        signal_name="classifier_stage3",
        label=None,
        trigger="Classifier(stub_no_op)",
        score_or_note="",
    )
    return current_label, "Classifier(stub_no_op)", [sig]


__all__ = ["classifier_upgrade_only"]
