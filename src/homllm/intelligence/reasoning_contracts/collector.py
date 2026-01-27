"""
Reasoning Contract Collector

Optional enable/disable wrapper for contract building.
Returns empty contract when disabled.

CONSTRAINTS (ABSOLUTE):
- Returns empty contract when disabled
- No side effects
- Purely declarative
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homllm.intelligence.reasoning_contracts.interfaces import ReasoningContract
from homllm.intelligence.reasoning_contracts.builder import ContractBuilder

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact
    from homllm.intelligence.reasoning_diagnostic import ReasoningDiagnosticResult
    from homllm.intelligence.assertion_readability import ReadabilityResult


class ContractCollector:
    """
    Optional collector for reasoning contract building.
    
    Wraps the builder and provides enable/disable control.
    When disabled, returns empty contract with no computation.
    """
    
    def __init__(self, enabled: bool = False):
        """
        Initialize the collector.
        
        Args:
            enabled: Whether to build reasoning contracts.
        """
        self._enabled = enabled
        self._builder = ContractBuilder()
    
    @property
    def enabled(self) -> bool:
        """Check if contract building is enabled."""
        return self._enabled
    
    def collect(
        self,
        diagnostic_result: "ReasoningDiagnosticResult",
        readability_result: "ReadabilityResult",
        context: "ContextArtifact",
    ) -> ReasoningContract:
        """
        Collect reasoning contract.
        
        Args:
            diagnostic_result: Result from Phase-1 RDL evaluation
            readability_result: Result from ARM evaluation
            context: Original ContextArtifact
            
        Returns:
            ReasoningContract with required steps.
            Empty contract if collector is disabled.
        """
        if not self._enabled:
            return ReasoningContract.empty()
        
        return self._builder.build(
            diagnostic_result=diagnostic_result,
            readability_result=readability_result,
            context=context,
        )


def create_contract_collector(enabled: bool = False) -> ContractCollector:
    """
    Factory function to create a ContractCollector.
    
    Args:
        enabled: Whether to enable contract building
        
    Returns:
        Configured ContractCollector
    """
    return ContractCollector(enabled=enabled)


__all__ = [
    "ContractCollector",
    "create_contract_collector",
]
