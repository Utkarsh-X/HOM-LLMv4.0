"""
Historical Failure Pattern Frequency (spec § Signal 3, § Anti-Amplification).

Frequency of Problem 1/2 downgrades per bucket. Only raw counters influence labels.
"""

from __future__ import annotations

from homllm.instability.interfaces import PrimaryLabelType, RunRecord


def failure_frequency(runs: tuple[RunRecord, ...]) -> tuple[float, PrimaryLabelType | None]:
    """
    Instability from historical failure frequency. Only raw runs (not policy_influenced).
    Recurring misalignment → UNSTABLE_CONTEXT.
    """
    raw_runs = [r for r in runs if not r.policy_influenced]
    if not raw_runs:
        return 0.0, None
    failures = sum(1 for r in raw_runs if r.final_verdict != "SUFFICIENT")
    score = failures / len(raw_runs)
    label: PrimaryLabelType | None = "UNSTABLE_CONTEXT" if score > 0.5 else None
    return score, label
