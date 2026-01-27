"""
Reasoning Diagnostic Layer - Data Structures

Read-only data structures for reasoning diagnostic evaluation.
This module defines types that classify reasoning failures in
generated answers without modifying generation behavior.

CONSTRAINTS (ABSOLUTE):
- All types are frozen (immutable)
- No behavior logic
- No thresholds or probabilities
- Purely descriptive
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class QueryTypeFlag(Enum):
    """
    Flags indicating the type of reasoning expected from a query.
    
    Detected via keyword matching, not interpretation.
    """
    
    ENUMERATIVE = "enumerative"       # "all", "list", "how many", "every"
    INTERACTIONAL = "interactional"   # "interact", "combine", "between"
    TRACE = "trace"                   # "trace", "flow", "execution"


class DiagnosticConfidence(Enum):
    """
    Confidence level based on binary evidence presence.
    
    NOT probability — just evidence count.
    """
    
    STRONG = "strong"       # Multiple binary evidence present
    MODERATE = "moderate"   # Single evidence present
    WEAK = "weak"           # No strong evidence


@dataclass(frozen=True)
class ReasoningExpectation:
    """
    What the query expects from the answer.
    
    Derived deterministically from query keywords.
    """
    
    aggregation_expected: bool    # Query implies enumeration
    interaction_expected: bool    # Query implies component interaction
    trace_expected: bool          # Query implies execution flow


@dataclass(frozen=True)
class ReasoningFailure:
    """
    Classification of reasoning failures detected in the answer.
    
    Binary flags, no fuzzy logic.
    """
    
    aggregation_missing: bool     # Expected enumeration not provided
    interaction_missing: bool     # Components not connected
    premature_surrender: bool     # Claims "not found" despite readable context


@dataclass(frozen=True)
class EvidenceSummary:
    """
    Summary of evidence used for classification.
    """
    
    readable_blocks: int
    distinct_components_detected: int
    enumeration_markers_found: bool
    interaction_markers_found: bool
    surrender_phrases_found: bool


@dataclass(frozen=True)
class ReasoningDiagnosticResult:
    """
    Complete reasoning diagnostic result.
    
    Aggregates query expectations, detected failures, and evidence.
    """
    
    query_type_flags: tuple[QueryTypeFlag, ...]
    expectations: ReasoningExpectation
    failures: ReasoningFailure
    evidence: EvidenceSummary
    confidence: DiagnosticConfidence
    
    @classmethod
    def empty(cls) -> "ReasoningDiagnosticResult":
        """Create an empty diagnostic result."""
        return cls(
            query_type_flags=(),
            expectations=ReasoningExpectation(
                aggregation_expected=False,
                interaction_expected=False,
                trace_expected=False,
            ),
            failures=ReasoningFailure(
                aggregation_missing=False,
                interaction_missing=False,
                premature_surrender=False,
            ),
            evidence=EvidenceSummary(
                readable_blocks=0,
                distinct_components_detected=0,
                enumeration_markers_found=False,
                interaction_markers_found=False,
                surrender_phrases_found=False,
            ),
            confidence=DiagnosticConfidence.WEAK,
        )
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for telemetry output."""
        return {
            "query_type_flags": [f.value for f in self.query_type_flags],
            "expectations": {
                "aggregation_expected": self.expectations.aggregation_expected,
                "interaction_expected": self.expectations.interaction_expected,
                "trace_expected": self.expectations.trace_expected,
            },
            "failures": {
                "aggregation_missing": self.failures.aggregation_missing,
                "interaction_missing": self.failures.interaction_missing,
                "premature_surrender": self.failures.premature_surrender,
            },
            "evidence": {
                "readable_blocks": self.evidence.readable_blocks,
                "distinct_components_detected": self.evidence.distinct_components_detected,
                "enumeration_markers_found": self.evidence.enumeration_markers_found,
                "interaction_markers_found": self.evidence.interaction_markers_found,
                "surrender_phrases_found": self.evidence.surrender_phrases_found,
            },
            "confidence": self.confidence.value,
        }
    
    @property
    def has_failures(self) -> bool:
        """Check if any failures were detected."""
        return (
            self.failures.aggregation_missing
            or self.failures.interaction_missing
            or self.failures.premature_surrender
        )


__all__ = [
    "QueryTypeFlag",
    "DiagnosticConfidence",
    "ReasoningExpectation",
    "ReasoningFailure",
    "EvidenceSummary",
    "ReasoningDiagnosticResult",
]
