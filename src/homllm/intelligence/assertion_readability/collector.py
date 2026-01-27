"""
Assertion Readability Collector

Optional telemetry collector for readability evaluation.
Wraps the evaluator with enable/disable logic.

CONSTRAINTS (ABSOLUTE):
- Returns empty result when disabled
- No side effects
- Purely observational
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homllm.intelligence.assertion_readability.interfaces import ReadabilityResult
from homllm.intelligence.assertion_readability.evaluator import (
    AssertionReadabilityEvaluator,
)

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact
    from homllm.intelligence.interfaces import DiagnosticSnapshot
    from homllm.intelligence.controller import ContextModificationPlan


class ReadabilityCollector:
    """
    Optional collector for assertion readability evaluation.
    
    Wraps the evaluator and provides enable/disable control.
    When disabled, returns empty result with no computation.
    
    Usage:
        collector = ReadabilityCollector(enabled=True)
        result = collector.collect(snapshot, plan, context)
    """
    
    def __init__(self, enabled: bool = False):
        """
        Initialize the collector.
        
        Args:
            enabled: Whether to perform readability evaluation.
                     When False, collect() returns empty result.
        """
        self._enabled = enabled
        self._evaluator = AssertionReadabilityEvaluator()
    
    @property
    def enabled(self) -> bool:
        """Check if readability evaluation is enabled."""
        return self._enabled
    
    def collect(
        self,
        snapshot: "DiagnosticSnapshot",
        plan: "ContextModificationPlan",
        context: "ContextArtifact",
    ) -> ReadabilityResult:
        """
        Collect readability evaluation results.
        
        Args:
            snapshot: DiagnosticSnapshot from diagnostics engine
            plan: ContextModificationPlan from intelligence controller
            context: Original ContextArtifact (read-only)
            
        Returns:
            ReadabilityResult with per-block assessments.
            Empty result if collector is disabled.
        """
        if not self._enabled:
            return ReadabilityResult.empty()
        
        return self._evaluator.evaluate(snapshot, plan, context)


def create_readability_collector(enabled: bool = False) -> ReadabilityCollector:
    """
    Factory function to create a ReadabilityCollector.
    
    Args:
        enabled: Whether to enable readability evaluation
        
    Returns:
        Configured ReadabilityCollector
    """
    return ReadabilityCollector(enabled=enabled)


__all__ = [
    "ReadabilityCollector",
    "create_readability_collector",
]
