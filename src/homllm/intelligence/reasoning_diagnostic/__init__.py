"""
Reasoning Diagnostic Layer (RDL) Module

Read-only layer that identifies where and why reasoning stops
prematurely in generated answers, without modifying generation behavior.

Detects:
- Aggregation missing (enumeration expected but not provided)
- Interaction missing (components not connected)
- Premature surrender (claims "not found" despite readable context)

This module is OPTIONAL and does NOT affect system behavior.
Enable via --reasoning-diagnostics CLI flag.

Exports:
- ReasoningDiagnosticEvaluator: Main evaluator class
- ReasoningDiagnosticResult: Evaluation output data structure
- QueryTypeFlag: Query type classification enum
- ReasoningFailure: Failure classification dataclass
"""

from homllm.intelligence.reasoning_diagnostic.interfaces import (
    QueryTypeFlag,
    DiagnosticConfidence,
    ReasoningExpectation,
    ReasoningFailure,
    EvidenceSummary,
    ReasoningDiagnosticResult,
)

from homllm.intelligence.reasoning_diagnostic.evaluator import (
    ReasoningDiagnosticEvaluator,
    create_reasoning_evaluator,
)

from homllm.intelligence.reasoning_diagnostic.collector import (
    ReasoningDiagnosticCollector,
    create_reasoning_collector,
)


__all__ = [
    # Data structures
    "QueryTypeFlag",
    "DiagnosticConfidence",
    "ReasoningExpectation",
    "ReasoningFailure",
    "EvidenceSummary",
    "ReasoningDiagnosticResult",
    # Evaluator
    "ReasoningDiagnosticEvaluator",
    "create_reasoning_evaluator",
    # Collector
    "ReasoningDiagnosticCollector",
    "create_reasoning_collector",
]
