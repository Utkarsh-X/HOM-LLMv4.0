"""
Adapter: Problem‑1 SufficiencyResult → Problem‑2 RemediationInput (spec §3).

Derives failed_axes and final_label from P1 output. Does not infer missing data.
"""

from __future__ import annotations

from homllm.remediation.interfaces import (
    FinalLabelType,
    RemediationInput,
)
from homllm.sufficiency.interfaces import SufficiencyResult, VerdictType

# P1 verdict → P2 final_label (spec §3)
_VERDICT_TO_LABEL: dict[VerdictType, FinalLabelType] = {
    "SUFFICIENT": "ALIGNED",
    "PROBABLY_SUFFICIENT": "PARTIALLY_ALIGNED",
    "INSUFFICIENT": "MISALIGNED",
}

# P1 signal key → axis name for failed_axes
_SIGNAL_KEY_TO_AXIS: dict[str, str] = {
    "semantic": "SEMANTIC",
    "rule": "RULE",
    "structural": "STRUCTURAL",
}


def sufficiency_to_remediation_input(
    result: SufficiencyResult,
    *,
    fragility_flag: bool = False,
) -> RemediationInput:
    """
    Convert Problem‑1 SufficiencyResult to Problem‑2 RemediationInput.

    Derives:
    - final_label from final_verdict (ALIGNED / PARTIALLY_ALIGNED / MISALIGNED)
    - failed_axes from signals where label == INSUFFICIENT
    - deciding_factor and intent_class from result

    Does not infer: negative_evidence, confidence left empty/None if not present.
    fragility_flag is optional; pass True when historical fragility is known (e.g. from run history).
    """
    final_label = _VERDICT_TO_LABEL[result.final_verdict]
    deciding_factor = result.deciding_factor  # AxisType | None
    intent_class = result.intent  # IntentType is str

    failed_axes_list: list[str] = []
    for key, sig in result.signals.items():
        if sig.label == "INSUFFICIENT":
            axis = _SIGNAL_KEY_TO_AXIS.get(key)
            if axis:
                failed_axes_list.append(axis)

    return RemediationInput(
        final_label=final_label,
        deciding_factor=deciding_factor,  # type: ignore[arg-type]
        intent_class=intent_class,
        failed_axes=tuple(failed_axes_list),
        negative_evidence=(),
        confidence=None,
        fragility_flag=fragility_flag,
    )


__all__ = ["sufficiency_to_remediation_input"]
