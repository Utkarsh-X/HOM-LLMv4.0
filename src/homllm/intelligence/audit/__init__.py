"""
Assertion Suppression Audit Module

Read-only observability layer for explaining why assertions
are suppressed by intelligence actions.

This module is OPTIONAL and does NOT affect system behavior.
Enable via --assertion-audit CLI flag.

Exports:
- AuditCollector: Main collector class
- AuditResult: Audit output data structure
- AssertionCandidate: Potential assertion representation
- SuppressionReason: Explanation for suppression
"""

from homllm.intelligence.audit.interfaces import (
    AssertionCandidate,
    SuppressionReason,
    AssertionAuditEntry,
    AuditResult,
)

from homllm.intelligence.audit.collector import (
    AuditCollector,
    create_audit_collector,
)


__all__ = [
    # Data structures
    "AssertionCandidate",
    "SuppressionReason",
    "AssertionAuditEntry",
    "AuditResult",
    # Collector
    "AuditCollector",
    "create_audit_collector",
]
