"""Sufficiency signals: semantic, rule, structural. Deterministic, read-only."""

from homllm.sufficiency.signals.semantic import compute_semantic_signal
from homllm.sufficiency.signals.rule import compute_rule_signal
from homllm.sufficiency.signals.structural import compute_structural_signal

__all__ = [
    "compute_semantic_signal",
    "compute_rule_signal",
    "compute_structural_signal",
]
