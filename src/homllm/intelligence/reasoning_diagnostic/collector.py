"""
Reasoning Diagnostic Collector

Optional enable/disable wrapper for reasoning diagnostics.
Returns empty result when disabled.

CONSTRAINTS (ABSOLUTE):
- Returns empty result when disabled
- No side effects
- Purely observational
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homllm.intelligence.reasoning_diagnostic.interfaces import (
    ReasoningDiagnosticResult,
)
from homllm.intelligence.reasoning_diagnostic.evaluator import (
    ReasoningDiagnosticEvaluator,
)

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact
    from homllm.intelligence.assertion_readability import ReadabilityResult


class ReasoningDiagnosticCollector:
    """
    Optional collector for reasoning diagnostic evaluation.
    
    Wraps the evaluator and provides enable/disable control.
    When disabled, returns empty result with no computation.
    """
    
    def __init__(self, enabled: bool = False):
        """
        Initialize the collector.
        
        Args:
            enabled: Whether to perform reasoning diagnostics.
        """
        self._enabled = enabled
        self._evaluator = ReasoningDiagnosticEvaluator()
    
    @property
    def enabled(self) -> bool:
        """Check if reasoning diagnostics are enabled."""
        return self._enabled
    
    def collect(
        self,
        query_text: str,
        answer_text: str,
        readability_result: "ReadabilityResult",
        context: "ContextArtifact",
    ) -> ReasoningDiagnosticResult:
        """
        Collect reasoning diagnostic results.
        
        Args:
            query_text: Original query string
            answer_text: Generated answer text
            readability_result: Result from ARM evaluation
            context: Original ContextArtifact
            
        Returns:
            ReasoningDiagnosticResult with classifications.
            Empty result if collector is disabled.
        """
        if not self._enabled:
            return ReasoningDiagnosticResult.empty()
        
        return self._evaluator.evaluate(
            query_text=query_text,
            answer_text=answer_text,
            readability_result=readability_result,
            context=context,
        )


def create_reasoning_collector(enabled: bool = False) -> ReasoningDiagnosticCollector:
    """
    Factory function to create a ReasoningDiagnosticCollector.
    
    Args:
        enabled: Whether to enable reasoning diagnostics
        
    Returns:
        Configured ReasoningDiagnosticCollector
    """
    return ReasoningDiagnosticCollector(enabled=enabled)


__all__ = [
    "ReasoningDiagnosticCollector",
    "create_reasoning_collector",
]
