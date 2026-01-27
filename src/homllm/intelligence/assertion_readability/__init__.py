"""
Assertion Readability Model (ARM) Module

Read-only layer that determines whether context blocks may be
asserted by the LLM, separating mutability safety from epistemic usability.

Core Principle: Protection ≠ Silence
A block may be non-removable but still assertable.

This module is OPTIONAL and does NOT affect system behavior.
Enable via --assertion-readability CLI flag.

Exports:
- AssertionReadabilityEvaluator: Main evaluator class
- ReadabilityResult: Evaluation output data structure
- AssertionReadability: Per-block readability assessment
- ReadabilityReason: Enum of readability reasons
"""

from homllm.intelligence.assertion_readability.interfaces import (
    ReadabilityReason,
    AssertionReadability,
    ReadabilityResult,
)

from homllm.intelligence.assertion_readability.evaluator import (
    AssertionReadabilityEvaluator,
    create_readability_evaluator,
)

from homllm.intelligence.assertion_readability.collector import (
    ReadabilityCollector,
    create_readability_collector,
)


__all__ = [
    # Data structures
    "ReadabilityReason",
    "AssertionReadability",
    "ReadabilityResult",
    # Evaluator
    "AssertionReadabilityEvaluator",
    "create_readability_evaluator",
    # Collector
    "ReadabilityCollector",
    "create_readability_collector",
]
