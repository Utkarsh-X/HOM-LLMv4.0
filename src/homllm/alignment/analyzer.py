"""
Alignment Analyzer - Main Orchestrator

Computes complete AlignmentReport from query and context.
Orchestrates semantic, structural, and grounding signal computation.

CONSTRAINTS:
- Read-only, deterministic
- Zero runtime cost when disabled
- No side effects on context or plans
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact
    from homllm.indexer.embedder import QwenEmbedder
    from homllm.intelligence.reasoning_contracts.interfaces import ReasoningContract
    from homllm.intelligence.assertion_readability.interfaces import ReadabilityResult

from .interfaces import (
    AlignmentReport,
    RiskIndicators,
)
from .semantic import compute_semantic_alignment
from .structural import compute_structural_alignment
from .grounding import compute_grounding_alignment


logger = logging.getLogger(__name__)


def _derive_risk_indicators(
    semantic_mean: float,
    semantic_variance: float,
    structural_gap_ratio: float,
    grounding_pressure: float,
) -> RiskIndicators:
    """
    Derive qualitative risk labels from numeric signals.
    
    Labels are for observability ONLY and do NOT affect behavior.
    
    Thresholds are deterministic and fixed:
    - semantic_drift: based on mean similarity
    - structural_gap: based on ratio of unsupported steps
    - grounding_pressure: based on pressure ratio
    """
    # Semantic drift: low mean similarity or high variance
    if semantic_mean < 0.3 or semantic_variance > 0.1:
        semantic_drift = "high"
    elif semantic_mean < 0.5 or semantic_variance > 0.05:
        semantic_drift = "medium"
    else:
        semantic_drift = "low"
    
    # Structural gap: ratio of unsupported to expected steps
    if structural_gap_ratio > 0.5:
        structural_gap = "high"
    elif structural_gap_ratio > 0.2:
        structural_gap = "medium"
    else:
        structural_gap = "low"
    
    # Grounding pressure: claim to capacity ratio
    if grounding_pressure > 2.0:
        grounding_pressure_label = "high"
    elif grounding_pressure > 1.0:
        grounding_pressure_label = "medium"
    else:
        grounding_pressure_label = "low"
    
    return RiskIndicators(
        semantic_drift=semantic_drift,
        structural_gap=structural_gap,
        grounding_pressure=grounding_pressure_label,
    )


class AlignmentAnalyzer:
    """
    Level-1 Alignment Analyzer.
    
    Computes alignment signals between query, context, and expected
    answer structure. Produces a frozen, immutable AlignmentReport.
    
    CONSTRAINTS:
    - Read-only (never modifies inputs)
    - Deterministic (same input → same output)
    - Zero cost when disabled (returns None immediately)
    - Provider-agnostic (uses existing embedder)
    """
    
    def __init__(
        self,
        embedder: "QwenEmbedder",
        enabled: bool = False,
    ):
        """
        Initialize alignment analyzer.
        
        Args:
            embedder: Embedding model for semantic similarity
            enabled: Whether alignment analysis is active
        """
        self._embedder = embedder
        self._enabled = enabled
    
    @property
    def enabled(self) -> bool:
        """Check if analyzer is enabled."""
        return self._enabled
    
    def analyze(
        self,
        query: str,
        context_artifact: "ContextArtifact",
        reasoning_contract: Optional["ReasoningContract"] = None,
        readability_result: Optional["ReadabilityResult"] = None,
    ) -> Optional[AlignmentReport]:
        """
        Compute complete alignment report.
        
        Args:
            query: User query string
            context_artifact: Assembled context with blocks
            reasoning_contract: Optional reasoning contract
            readability_result: Optional readability evaluation
            
        Returns:
            AlignmentReport if enabled, None otherwise
            
        GUARANTEES:
        - Deterministic output
        - Zero runtime cost when disabled
        - No side effects
        """
        if not self._enabled:
            return None
        
        logger.debug("Computing alignment signals...")
        
        # Compute semantic alignment (QCSA)
        semantic = compute_semantic_alignment(
            query=query,
            context_artifact=context_artifact,
            embedder=self._embedder,
        )
        
        # Compute structural alignment (SEG)
        structural = compute_structural_alignment(
            context_artifact=context_artifact,
            reasoning_contract=reasoning_contract,
            readability_result=readability_result,
        )
        
        # Compute grounding alignment (GCS)
        grounding = compute_grounding_alignment(
            context_artifact=context_artifact,
            reasoning_contract=reasoning_contract,
            readability_result=readability_result,
        )
        
        # Compute structural gap ratio for risk indicators
        if structural.expected_reasoning_steps > 0:
            unsupported_count = sum(
                1 for supported in structural.structural_support_matrix.values()
                if not supported
            )
            structural_gap_ratio = unsupported_count / structural.expected_reasoning_steps
        else:
            structural_gap_ratio = 0.0
        
        # Derive risk indicators
        risk_indicators = _derive_risk_indicators(
            semantic_mean=semantic.mean_similarity,
            semantic_variance=semantic.similarity_variance,
            structural_gap_ratio=structural_gap_ratio,
            grounding_pressure=grounding.grounding_pressure_ratio,
        )
        
        report = AlignmentReport(
            semantic_alignment=semantic,
            structural_alignment=structural,
            grounding_alignment=grounding,
            risk_indicators=risk_indicators,
        )
        
        logger.debug(
            f"Alignment computed: semantic_mean={semantic.mean_similarity:.3f}, "
            f"structural_steps={structural.expected_reasoning_steps}, "
            f"grounding_pressure={grounding.grounding_pressure_ratio:.3f}"
        )
        
        return report


__all__ = ["AlignmentAnalyzer"]
