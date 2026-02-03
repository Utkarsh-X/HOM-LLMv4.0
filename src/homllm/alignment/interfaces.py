"""
Level-1 Alignment Observability Layer - Data Structures

Read-only, frozen data structures for alignment signals.
This module exposes measurable alignment indicators between
query, context, and expected answer structure.

CONSTRAINTS (ABSOLUTE):
- All types are frozen (immutable)
- No behavior logic
- No thresholds for decisions
- Purely descriptive telemetry
- Deterministic output
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SemanticAlignment:
    """
    Query–Context Semantic Alignment (QCSA) signals.
    
    Measures semantic similarity between query and context blocks
    using embedding cosine similarity.
    
    Attributes:
        mean_similarity: Average cosine similarity across all blocks
        min_similarity: Minimum block similarity
        max_similarity: Maximum block similarity  
        similarity_variance: Variance of similarity distribution
        outlier_block_count: Blocks far from mean (>2 std deviations)
        block_similarities: Raw per-block similarity values
    """
    
    mean_similarity: float
    min_similarity: float
    max_similarity: float
    similarity_variance: float
    outlier_block_count: int
    block_similarities: tuple[float, ...]
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for telemetry."""
        return {
            "mean_similarity": round(self.mean_similarity, 4),
            "min_similarity": round(self.min_similarity, 4),
            "max_similarity": round(self.max_similarity, 4),
            "similarity_variance": round(self.similarity_variance, 6),
            "outlier_block_count": self.outlier_block_count,
            "block_count": len(self.block_similarities),
        }
    
    @classmethod
    def empty(cls) -> "SemanticAlignment":
        """Create empty semantic alignment result."""
        return cls(
            mean_similarity=0.0,
            min_similarity=0.0,
            max_similarity=0.0,
            similarity_variance=0.0,
            outlier_block_count=0,
            block_similarities=(),
        )


@dataclass(frozen=True)
class StructuralAlignment:
    """
    Structural Expectation Gap (SEG) signals.
    
    Exposes whether expected answer structure is supported
    by available context.
    
    Attributes:
        expected_reasoning_steps: Count of required reasoning steps from contract
        readable_block_count: Blocks that can be asserted by LLM
        distinct_component_count: Unique files/components in context
        structural_support_matrix: Map of step name → whether supported
    """
    
    expected_reasoning_steps: int
    readable_block_count: int
    distinct_component_count: int
    structural_support_matrix: dict[str, bool]
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for telemetry."""
        return {
            "expected_reasoning_steps": self.expected_reasoning_steps,
            "readable_block_count": self.readable_block_count,
            "distinct_component_count": self.distinct_component_count,
            "structural_support_matrix": self.structural_support_matrix,
        }
    
    @classmethod
    def empty(cls) -> "StructuralAlignment":
        """Create empty structural alignment result."""
        return cls(
            expected_reasoning_steps=0,
            readable_block_count=0,
            distinct_component_count=0,
            structural_support_matrix={},
        )


@dataclass(frozen=True)
class GroundingAlignment:
    """
    Grounding Coverage Signal (GCS).
    
    Estimates whether context can support expected claim count.
    
    Attributes:
        estimated_claim_count: Expected claims from reasoning requirements
        grounding_reference_capacity: Available grounding from readable blocks
        grounding_pressure_ratio: claims / capacity (higher = more pressure)
    """
    
    estimated_claim_count: int
    grounding_reference_capacity: int
    grounding_pressure_ratio: float
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for telemetry."""
        return {
            "estimated_claim_count": self.estimated_claim_count,
            "grounding_reference_capacity": self.grounding_reference_capacity,
            "grounding_pressure_ratio": round(self.grounding_pressure_ratio, 4),
        }
    
    @classmethod
    def empty(cls) -> "GroundingAlignment":
        """Create empty grounding alignment result."""
        return cls(
            estimated_claim_count=0,
            grounding_reference_capacity=0,
            grounding_pressure_ratio=0.0,
        )


@dataclass(frozen=True)
class RiskIndicators:
    """
    Qualitative risk labels derived from alignment signals.
    
    These labels are for observability ONLY and do NOT affect
    any system behavior.
    
    Attributes:
        semantic_drift: "low" | "medium" | "high"
        structural_gap: "low" | "medium" | "high"
        grounding_pressure: "low" | "medium" | "high"
    """
    
    semantic_drift: str
    structural_gap: str
    grounding_pressure: str
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for telemetry."""
        return {
            "semantic_drift": self.semantic_drift,
            "structural_gap": self.structural_gap,
            "grounding_pressure": self.grounding_pressure,
        }
    
    @classmethod
    def empty(cls) -> "RiskIndicators":
        """Create empty risk indicators."""
        return cls(
            semantic_drift="low",
            structural_gap="low",
            grounding_pressure="low",
        )


@dataclass(frozen=True)
class AlignmentReport:
    """
    Complete Level-1 Alignment Report.
    
    Produced once per query, after context assembly and before generation.
    Contains all alignment signals for telemetry/observability.
    
    CONSTRAINTS:
    - Frozen (immutable)
    - JSON-serializable
    - Deterministic
    """
    
    semantic_alignment: SemanticAlignment
    structural_alignment: StructuralAlignment
    grounding_alignment: GroundingAlignment
    risk_indicators: RiskIndicators
    
    def to_dict(self) -> dict:
        """Serialize to dictionary for telemetry output."""
        return {
            "semantic_alignment": self.semantic_alignment.to_dict(),
            "structural_alignment": self.structural_alignment.to_dict(),
            "grounding_alignment": self.grounding_alignment.to_dict(),
            "risk_indicators": self.risk_indicators.to_dict(),
        }
    
    @classmethod
    def empty(cls) -> "AlignmentReport":
        """Create empty alignment report."""
        return cls(
            semantic_alignment=SemanticAlignment.empty(),
            structural_alignment=StructuralAlignment.empty(),
            grounding_alignment=GroundingAlignment.empty(),
            risk_indicators=RiskIndicators.empty(),
        )


__all__ = [
    "SemanticAlignment",
    "StructuralAlignment",
    "GroundingAlignment",
    "RiskIndicators",
    "AlignmentReport",
]
