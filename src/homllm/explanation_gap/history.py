"""
Stage 1 — Historical depth recurrence (spec §4.4, §5).

Read-only statistics per bucket. Cold-start → conservative (no downgrade).
Escalation only when history indicates depth recurrence.
"""

from __future__ import annotations

from homllm.explanation_gap.constants import HISTORY_ESCALATION_PCT
from homllm.explanation_gap.interfaces import (
    DepthLabelType,
    HistoryDepthStats,
    SignalOutput,
    max_severity,
)


def historical_depth_escalation(
    current_label: DepthLabelType,
    stats: HistoryDepthStats | None,
) -> tuple[DepthLabelType, str, list[SignalOutput]]:
    """
    Stage 1 historical signal. Only escalates; never downgrades.
    Cold-start (stats None or low volume) → no change.
    When pct_expanded_or_manual or pct_shallow_complaints >= threshold → upgrade to DETAILED_REQUIRED.
    """
    if stats is None or stats.runs_in_bucket < 2:
        sig = SignalOutput(
            signal_name="historical_depth",
            label=None,
            trigger="History(cold_start)",
            score_or_note="insufficient_evidence",
        )
        return current_label, "History(cold_start)", [sig]

    pct_expanded = stats.pct_expanded_or_manual
    pct_complaints = stats.pct_shallow_complaints
    if pct_expanded >= HISTORY_ESCALATION_PCT or pct_complaints >= HISTORY_ESCALATION_PCT:
        # Escalate at least to DETAILED_REQUIRED; never downgrade
        upgraded = max_severity(current_label, "DETAILED_REQUIRED")
        trigger = "History(expand_or_complaint)"
        sig = SignalOutput(
            signal_name="historical_depth",
            label=upgraded,
            trigger=trigger,
            score_or_note=f"pct_expanded={pct_expanded:.2f}, pct_complaints={pct_complaints:.2f}",
        )
        return upgraded, trigger, [sig]

    sig = SignalOutput(
        signal_name="historical_depth",
        label=None,
        trigger="History(no_escalation)",
        score_or_note=f"runs={stats.runs_in_bucket}",
    )
    return current_label, "History(no_escalation)", [sig]


__all__ = ["historical_depth_escalation"]
