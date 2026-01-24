"""
Diagnostic Engine Interface

Exposes L1-L3 diagnostics through a clean, stable interface layer.
This is the ONLY gateway for Action Engines to observe diagnostic state.

DESIGN CONSTRAINTS (ABSOLUTE):
- No action logic, thresholds, or rules
- No context mutation or feedback loops
- No learning, memory, or caching
- No side effects (logging, printing, formatting)
- Deterministic: same input → same output
- Query-scoped: operates on one ContextArtifact at a time

The interface wraps diagnostics, it does NOT replace them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact

# Import diagnostic result types (read-only access)
from homllm.intelligence.diagnostics.inspect_context import (
    IntraBlockDiagnostic,
    ContextDiagnosticResult,
)
from homllm.intelligence.diagnostics.inspect_context_relations import (
    RelationalDiagnosticResult,
)
from homllm.intelligence.diagnostics.context_level3.inspect_alignment_summary import (
    Level3DiagnosticResult,
)


# =============================================================================
# LEVEL CONTAINERS (Typed Wrappers)
# =============================================================================

@dataclass(frozen=True)
class StructuralDiagnostics:
    """
    Level-1 wrapper: Structural diagnostics.
    
    Includes:
    - Token counts and breakdown
    - Noise ratios and signal ratios
    - Redundancy flags
    - Block composition analysis
    - Budget pressure indicators
    - Structural dominance metrics
    
    Preserves original metrics, adds no interpretation.
    """
    
    status: Literal["available", "unavailable"]
    reason: str  # Empty string if available, explanation if unavailable
    
    # Per-block intra-block diagnostics
    blocks: tuple[IntraBlockDiagnostic, ...] = ()
    
    # Aggregate context-level result
    result: Optional[ContextDiagnosticResult] = None


@dataclass(frozen=True)
class SemanticDiagnostics:
    """
    Level-2 wrapper: Semantic diagnostics.
    
    Includes:
    - Concept maps and coverage
    - Semantic roles and relations
    - Obligation coverage analysis
    - Concept gaps
    - Alignment summaries
    - Semantic relations graph (similarity edges, redundancy clusters)
    
    Preserves original metrics, adds no interpretation.
    """
    
    status: Literal["available", "unavailable"]
    reason: str  # Empty string if available, explanation if unavailable
    
    # Relational analysis result
    result: Optional[RelationalDiagnosticResult] = None


@dataclass(frozen=True)
class CognitiveDiagnostics:
    """
    Level-3 wrapper: Cognitive diagnostics.
    
    Includes:
    - Cognitive load metrics per block
    - Reasoning depth analysis
    - Branching factor
    - Ambiguity indicators
    - Explanation anchors
    - Invariant presence detection
    - Query intent alignment
    - Explanatory role balance
    
    Preserves original metrics, adds no interpretation.
    """
    
    status: Literal["available", "unavailable"]
    reason: str  # Empty string if available, explanation if unavailable
    
    # Full Level-3 analysis result
    result: Optional[Level3DiagnosticResult] = None


# =============================================================================
# PRIMARY SNAPSHOT OBJECT
# =============================================================================

@dataclass(frozen=True)
class DiagnosticSnapshot:
    """
    The single object exposed to Action Engines.
    
    Contains exactly three sections for each diagnostic level.
    This is the ONLY way to access diagnostic state from outside
    the diagnostics module.
    
    Structure:
        DiagnosticSnapshot
        ├── level1: StructuralDiagnostics
        ├── level2: SemanticDiagnostics
        └── level3: CognitiveDiagnostics
    
    Guarantees:
    - Immutable (frozen dataclass)
    - All levels always present (never None at top level)
    - Failed diagnostics represented explicitly, not hidden
    - No interpretation or decision logic
    """
    
    level1: StructuralDiagnostics
    level2: SemanticDiagnostics
    level3: CognitiveDiagnostics
    
    @property
    def all_available(self) -> bool:
        """Check if all diagnostic levels are available."""
        return (
            self.level1.status == "available" and
            self.level2.status == "available" and
            self.level3.status == "available"
        )
    
    @property
    def any_unavailable(self) -> bool:
        """Check if any diagnostic level is unavailable."""
        return not self.all_available


# =============================================================================
# PROVIDER PROTOCOL
# =============================================================================

class DiagnosticProvider(Protocol):
    """
    Protocol for diagnostic providers.
    
    Defines the single entry point for producing DiagnosticSnapshots.
    Any concrete implementation must satisfy these contracts.
    
    Contract:
    - No side effects (no logging, printing, IO)
    - No mutations (context and state unchanged)
    - Deterministic (same input → same output)
    - Explicit failures (unavailable diagnostics represented, not hidden)
    - Query-scoped (operates on one ContextArtifact at a time)
    """
    
    def analyze(self, context: ContextArtifact) -> DiagnosticSnapshot:
        """
        Produce a diagnostic snapshot for the given context.
        
        Args:
            context: A single ContextArtifact to analyze
            
        Returns:
            DiagnosticSnapshot with all three levels populated.
            Failed levels have status="unavailable" with reason.
            
        Note:
            This method MUST NOT:
            - Log or print anything
            - Modify the context argument
            - Cache results internally
            - Perform any IO operations
            - Make decisions or optimizations
        """
        ...


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Level containers
    "StructuralDiagnostics",
    "SemanticDiagnostics",
    "CognitiveDiagnostics",
    # Primary object
    "DiagnosticSnapshot",
    # Protocol
    "DiagnosticProvider",
    # Re-exported result types for convenience
    "IntraBlockDiagnostic",
    "ContextDiagnosticResult",
    "RelationalDiagnosticResult",
    "Level3DiagnosticResult",
]
