"""
Action & Remediation Layer (Problem‑2).

Consumes Problem‑1 diagnostics; selects permissible corrective actions via deterministic
matrix. Does not diagnose, override vetoes, or mutate Problem‑1.
"""

from homllm.remediation.adapter import sufficiency_to_remediation_input
from homllm.remediation.interfaces import (
    ActionType,
    DecidingFactorType,
    FinalLabelType,
    RemediationAction,
    RemediationInput,
    RemediationResult,
)
from homllm.remediation.pipeline import run_remediation, run_remediation_from_sufficiency

__all__ = [
    "ActionType",
    "DecidingFactorType",
    "FinalLabelType",
    "RemediationAction",
    "RemediationInput",
    "RemediationResult",
    "run_remediation",
    "run_remediation_from_sufficiency",
    "sufficiency_to_remediation_input",
]
