"""
Level-2 Alignment Failure Classification

Deterministic, read-only failure classification layer that converts
Level-1 AlignmentReport signals into a minimal, stable failure taxonomy.

CONSTRAINTS (ABSOLUTE):
- No context mutation
- No retries or loops
- No intelligence invocation
- No generation influence
- Deterministic mapping only
- Same input → same output
- Fully removable with zero side effects
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .interfaces import AlignmentReport


class FailureType(str, Enum):
    """
    Failure taxonomy v1 (locked).
    
    Each failure type represents a distinct failure mode
    derived from Level-1 alignment signals.
    """
    
    SEMANTIC_DRIFT = "SEMANTIC_DRIFT"
    """Query intent likely mismatched with context."""
    
    STRUCTURAL_GAP = "STRUCTURAL_GAP"
    """Missing components or insufficient coverage."""
    
    GROUNDING_PRESSURE = "GROUNDING_PRESSURE"
    """Hallucination risk due to insufficient evidence."""
    
    OVERCONSTRAINED_CONTEXT = "OVERCONSTRAINED_CONTEXT"
    """"Correct-looking but wrong" answers risk."""
    
    UNDERCONSTRAINED_RESPONSE = "UNDERCONSTRAINED_RESPONSE"
    """Vague or incomplete outputs risk."""
    
    LOW_RISK = "LOW_RISK"
    """No failure modes detected."""


# Priority order for determining primary risk
_FAILURE_PRIORITY = (
    FailureType.GROUNDING_PRESSURE,
    FailureType.STRUCTURAL_GAP,
    FailureType.SEMANTIC_DRIFT,
    FailureType.OVERCONSTRAINED_CONTEXT,
    FailureType.UNDERCONSTRAINED_RESPONSE,
)


@dataclass(frozen=True)
class AlignmentFailureReport:
    """
    Frozen, serializable failure classification result.
    
    Produced by AlignmentClassifier from Level-1 AlignmentReport.
    
    Attributes:
        failures: Set of detected failure types (includes LOW_RISK if none)
        primary_risk: Highest priority failure, or None if LOW_RISK
        confidence: Deterministic confidence score (0-1)
        signals_used: Names of Level-1 signals consumed
    """
    
    failures: frozenset[FailureType]
    primary_risk: Optional[FailureType]
    confidence: float
    signals_used: frozenset[str]
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for telemetry output."""
        return {
            "failures": sorted([f.value for f in self.failures]),
            "primary_risk": self.primary_risk.value if self.primary_risk else None,
            "confidence": round(self.confidence, 2),
            "signals_used": sorted(list(self.signals_used)),
        }
    
    @classmethod
    def low_risk(cls, signals_used: frozenset[str]) -> "AlignmentFailureReport":
        """Create a LOW_RISK report when no failures detected."""
        return cls(
            failures=frozenset({FailureType.LOW_RISK}),
            primary_risk=None,
            confidence=1.0,
            signals_used=signals_used,
        )


# =============================================================================
# Threshold Constants (Deterministic, Fixed)
# =============================================================================

# Semantic drift thresholds
SEMANTIC_MEAN_THRESHOLD = 0.5
SEMANTIC_VARIANCE_THRESHOLD = 0.05

# Calibrated outlier thresholds (avoid false positives for benign single outliers)
SEMANTIC_OUTLIER_COUNT_THRESHOLD = 2  # Minimum outliers to trigger drift alone
SEMANTIC_OUTLIER_RATIO_THRESHOLD = 0.25  # 25% of blocks being outliers triggers drift
SEMANTIC_OUTLIER_MIN_BLOCKS = 1  # Minimum blocks for ratio calculation

# Grounding pressure threshold
GROUNDING_PRESSURE_THRESHOLD = 1.0


class AlignmentClassifier:
    """
    Level-2 failure classifier.
    
    Consumes AlignmentReport from Level-1 and produces
    AlignmentFailureReport with deterministic failure labels.
    
    CONSTRAINTS:
    - Read-only (never modifies input)
    - Deterministic (same input → same output)
    - Stateless (no instance state affects classification)
    - No side effects
    """
    
    def classify(self, report: "AlignmentReport") -> AlignmentFailureReport:
        """
        Classify Level-1 alignment report into failure modes.
        
        Args:
            report: Level-1 AlignmentReport
            
        Returns:
            Frozen AlignmentFailureReport with detected failures
            
        GUARANTEES:
        - Deterministic output
        - No side effects
        - No modification to input
        """
        failures: set[FailureType] = set()
        signals_used: set[str] = set()
        
        # Check SEMANTIC_DRIFT with calibrated thresholds
        semantic = report.semantic_alignment
        signals_used.add("semantic_alignment.mean_similarity")
        signals_used.add("semantic_alignment.similarity_variance")
        signals_used.add("semantic_alignment.outlier_block_count")
        signals_used.add("semantic_alignment.block_similarities")
        
        # Calculate outlier ratio for context-aware threshold
        total_blocks = len(semantic.block_similarities)
        outlier_count = semantic.outlier_block_count
        outlier_ratio = (
            outlier_count / total_blocks 
            if total_blocks >= SEMANTIC_OUTLIER_MIN_BLOCKS 
            else 0.0
        )
        
        # Semantic drift detection with calibrated thresholds:
        # 1. Low semantic mean always indicates drift
        # 2. High variance always indicates drift  
        # 3. Outliers only indicate drift when:
        #    - Multiple outliers exist (≥2), OR
        #    - High outlier ratio (≥25% of blocks), OR
        #    - Single outlier exists AND semantic mean is low (<0.5)
        semantic_drift_detected = False
        
        if semantic.mean_similarity < SEMANTIC_MEAN_THRESHOLD:
            semantic_drift_detected = True
        elif semantic.similarity_variance > SEMANTIC_VARIANCE_THRESHOLD:
            semantic_drift_detected = True
        elif outlier_count >= SEMANTIC_OUTLIER_COUNT_THRESHOLD:
            # Multiple outliers indicate real drift
            semantic_drift_detected = True
        elif outlier_ratio >= SEMANTIC_OUTLIER_RATIO_THRESHOLD:
            # High proportion of outliers indicates drift
            semantic_drift_detected = True
        elif outlier_count >= 1 and semantic.mean_similarity < SEMANTIC_MEAN_THRESHOLD:
            # Single outlier with weak mean indicates drift
            semantic_drift_detected = True
        
        if semantic_drift_detected:
            failures.add(FailureType.SEMANTIC_DRIFT)
        
        # Check STRUCTURAL_GAP
        structural = report.structural_alignment
        signals_used.add("structural_alignment.expected_reasoning_steps")
        signals_used.add("structural_alignment.readable_block_count")
        
        if structural.expected_reasoning_steps > structural.readable_block_count:
            failures.add(FailureType.STRUCTURAL_GAP)
        
        # Check GROUNDING_PRESSURE
        grounding = report.grounding_alignment
        signals_used.add("grounding_alignment.grounding_pressure_ratio")
        
        if grounding.grounding_pressure_ratio > GROUNDING_PRESSURE_THRESHOLD:
            failures.add(FailureType.GROUNDING_PRESSURE)
        
        # Check OVERCONSTRAINED_CONTEXT
        # Triggered when structure is enforced but semantic alignment is weak
        risk = report.risk_indicators
        signals_used.add("risk_indicators.structural_gap")
        signals_used.add("risk_indicators.semantic_drift")
        
        if risk.structural_gap == "low" and risk.semantic_drift == "high":
            failures.add(FailureType.OVERCONSTRAINED_CONTEXT)
        
        # Check UNDERCONSTRAINED_RESPONSE
        # Triggered when structure requirements exist but are weakly supported
        signals_used.add("structural_alignment.structural_support_matrix")
        
        if structural.expected_reasoning_steps > 0:
            unsupported_steps = sum(
                1 for supported in structural.structural_support_matrix.values()
                if not supported
            )
            if unsupported_steps > 0:
                failures.add(FailureType.UNDERCONSTRAINED_RESPONSE)
        
        # If no failures, return LOW_RISK
        frozen_signals = frozenset(signals_used)
        if not failures:
            return AlignmentFailureReport.low_risk(frozen_signals)
        
        # Determine primary risk by priority
        primary_risk: Optional[FailureType] = None
        for priority_failure in _FAILURE_PRIORITY:
            if priority_failure in failures:
                primary_risk = priority_failure
                break
        
        # Compute confidence based on number of signals indicating issues
        # More failures = lower confidence in output quality
        failure_count = len(failures)
        confidence = max(0.0, 1.0 - (failure_count * 0.15))
        
        return AlignmentFailureReport(
            failures=frozenset(failures),
            primary_risk=primary_risk,
            confidence=round(confidence, 2),
            signals_used=frozen_signals,
        )


def create_alignment_classifier() -> AlignmentClassifier:
    """
    Factory function to create AlignmentClassifier.
    
    Returns:
        Configured AlignmentClassifier instance
    """
    return AlignmentClassifier()


__all__ = [
    "FailureType",
    "AlignmentFailureReport",
    "AlignmentClassifier",
    "create_alignment_classifier",
]
