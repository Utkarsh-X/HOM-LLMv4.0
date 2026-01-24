"""
Module 5: Alignment Summary

Aggregates all Level-3 findings into a coherent diagnostic report.

Outputs:
- Query intent coverage score
- Explanation completeness score
- Cognitive risk flags
- Dominant failure mode

CONSTRAINTS:
- Deterministic heuristics only
- No ML/LLM
- Read-only
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from diagnostics.context.inspect_context import IntraBlockDiagnostic
from diagnostics.context_level3.inspect_query_intent import (
    QueryIntentAnalyzer,
    QueryIntent,
)
from diagnostics.context_level3.inspect_explanatory_roles import (
    ExplanatoryRoleAnalyzer,
    BlockRole,
    ExplanatoryRole,
)
from diagnostics.context_level3.inspect_concept_gaps import (
    ConceptGapAnalyzer,
    ConceptGapResult,
)
from diagnostics.context_level3.inspect_cognitive_load import (
    CognitiveLoadAnalyzer,
    CognitiveLoadResult,
    LoadLevel,
)


class FailureMode(Enum):
    """Dominant failure mode classification."""
    NONE = "None detected"
    MISSING_DEFINITION = "Missing conceptual definitions"
    MISSING_EXPLANATION = "Missing explanations despite implementation"
    IMPLEMENTATION_ONLY = "Implementation without context"
    HIGH_COGNITIVE_LOAD = "Excessive cognitive complexity"
    LOW_COVERAGE = "Insufficient concept coverage"
    ROLE_IMBALANCE = "Unbalanced explanatory roles"


@dataclass
class ExplanatoryBalance:
    """Balance of explanatory roles."""
    define_count: int = 0
    implement_count: int = 0
    explain_count: int = 0
    use_count: int = 0
    support_count: int = 0
    noise_count: int = 0
    
    # Assessment
    define_status: str = "sufficient"
    implement_status: str = "sufficient"
    explain_status: str = "sufficient"
    
    # Is balanced?
    is_balanced: bool = True


@dataclass
class Level3DiagnosticResult:
    """Complete Level-3 diagnostic result."""
    
    # Query intent
    intent: Optional[QueryIntent] = None
    
    # Block roles
    block_roles: list[BlockRole] = field(default_factory=list)
    
    # Concept gaps
    concept_gaps: Optional[ConceptGapResult] = None
    
    # Cognitive load
    cognitive_load: Optional[CognitiveLoadResult] = None
    
    # Summary metrics
    intent_coverage_score: float = 0.0
    explanation_completeness: float = 0.0
    
    # Role balance
    explanatory_balance: Optional[ExplanatoryBalance] = None
    
    # Failure mode
    primary_failure_mode: FailureMode = FailureMode.NONE
    
    # Missing concepts
    missing_concepts: list[str] = field(default_factory=list)
    
    # Warnings
    warnings: list[str] = field(default_factory=list)


class AlignmentSummaryAnalyzer:
    """
    Aggregates Level-3 analyses into final diagnostic report.
    
    Combines:
    - Query intent (Module 1)
    - Block roles (Module 2)
    - Concept gaps (Module 3)
    - Cognitive load (Module 4)
    """
    
    def __init__(self):
        self.intent_analyzer = QueryIntentAnalyzer()
        self.role_analyzer = ExplanatoryRoleAnalyzer()
        self.gap_analyzer = ConceptGapAnalyzer()
        self.load_analyzer = CognitiveLoadAnalyzer()
    
    def analyze(
        self,
        query: str,
        blocks: list[IntraBlockDiagnostic]
    ) -> Level3DiagnosticResult:
        """
        Run complete Level-3 analysis.
        
        Args:
            query: Query text
            blocks: Level-1 block diagnostics
            
        Returns:
            Complete Level-3 diagnostic result
        """
        result = Level3DiagnosticResult()
        
        # 1. Analyze query intent
        result.intent = self.intent_analyzer.analyze(query)
        
        # 2. Classify block roles
        result.block_roles = self.role_analyzer.analyze_blocks(blocks)
        
        # 3. Analyze concept gaps
        result.concept_gaps = self.gap_analyzer.analyze(
            result.intent,
            result.block_roles
        )
        
        # 4. Analyze cognitive load
        result.cognitive_load = self.load_analyzer.analyze(
            blocks,
            result.block_roles
        )
        
        # 5. Compute summary metrics
        result.intent_coverage_score = self._compute_intent_coverage(result)
        result.explanation_completeness = self._compute_explanation_completeness(result)
        
        # 6. Compute role balance
        result.explanatory_balance = self._compute_role_balance(result.block_roles)
        
        # 7. Identify missing concepts
        if result.concept_gaps:
            result.missing_concepts = [
                c.concept for c in result.concept_gaps.concept_coverage
                if not c.defined and not c.implemented and not c.explained
            ]
        
        # 8. Determine primary failure mode
        result.primary_failure_mode = self._determine_failure_mode(result)
        
        # 9. Aggregate warnings
        result.warnings = self._aggregate_warnings(result)
        
        return result
    
    def _compute_intent_coverage(self, result: Level3DiagnosticResult) -> float:
        """Compute intent coverage score."""
        if result.concept_gaps:
            return result.concept_gaps.overall_coverage_score
        return 0.0
    
    def _compute_explanation_completeness(
        self, 
        result: Level3DiagnosticResult
    ) -> float:
        """Compute explanation completeness."""
        if not result.block_roles:
            return 0.0
        
        explain_count = sum(
            1 for r in result.block_roles 
            if r.primary_role == ExplanatoryRole.EXPLAIN or
               r.secondary_role == ExplanatoryRole.EXPLAIN
        )
        
        define_count = sum(
            1 for r in result.block_roles
            if r.primary_role == ExplanatoryRole.DEFINE
        )
        
        # Good explanation: definitions + explanatory content
        total = len(result.block_roles)
        if total == 0:
            return 0.0
        
        return min(1.0, (explain_count + define_count) / total)
    
    def _compute_role_balance(
        self, 
        roles: list[BlockRole]
    ) -> ExplanatoryBalance:
        """Compute explanatory role balance."""
        balance = ExplanatoryBalance()
        
        for role in roles:
            if role.primary_role == ExplanatoryRole.DEFINE:
                balance.define_count += 1
            elif role.primary_role == ExplanatoryRole.IMPLEMENT:
                balance.implement_count += 1
            elif role.primary_role == ExplanatoryRole.EXPLAIN:
                balance.explain_count += 1
            elif role.primary_role == ExplanatoryRole.USE:
                balance.use_count += 1
            elif role.primary_role == ExplanatoryRole.SUPPORT:
                balance.support_count += 1
            elif role.primary_role == ExplanatoryRole.NOISE:
                balance.noise_count += 1
        
        total = len(roles)
        if total == 0:
            return balance
        
        # Assess balance
        if balance.define_count == 0 and balance.implement_count > 0:
            balance.define_status = "insufficient"
            balance.is_balanced = False
        
        if balance.implement_count > total * 0.7:
            balance.implement_status = "dominant"
            balance.is_balanced = False
        
        if balance.explain_count == 0 and total > 3:
            balance.explain_status = "insufficient"
            balance.is_balanced = False
        
        return balance
    
    def _determine_failure_mode(
        self, 
        result: Level3DiagnosticResult
    ) -> FailureMode:
        """Determine the primary failure mode."""
        # No failure if coverage is high
        if result.intent_coverage_score >= 0.8:
            if (result.cognitive_load and 
                result.cognitive_load.overall_load == LoadLevel.HIGH):
                return FailureMode.HIGH_COGNITIVE_LOAD
            return FailureMode.NONE
        
        # Check role balance issues
        if result.explanatory_balance:
            bal = result.explanatory_balance
            
            if bal.define_status == "insufficient":
                return FailureMode.MISSING_DEFINITION
            
            if bal.explain_status == "insufficient":
                return FailureMode.MISSING_EXPLANATION
            
            if bal.implement_status == "dominant":
                return FailureMode.IMPLEMENTATION_ONLY
        
        # Check concept gaps
        if result.concept_gaps and result.concept_gaps.uncovered > 0:
            return FailureMode.LOW_COVERAGE
        
        # Check cognitive load
        if (result.cognitive_load and 
            result.cognitive_load.overall_load == LoadLevel.HIGH):
            return FailureMode.HIGH_COGNITIVE_LOAD
        
        # Role imbalance
        if result.explanatory_balance and not result.explanatory_balance.is_balanced:
            return FailureMode.ROLE_IMBALANCE
        
        return FailureMode.NONE
    
    def _aggregate_warnings(
        self, 
        result: Level3DiagnosticResult
    ) -> list[str]:
        """Aggregate all warnings."""
        warnings = []
        
        # Concept gap warnings
        if result.concept_gaps and result.concept_gaps.warnings:
            warnings.extend(result.concept_gaps.warnings[:3])
        
        # Cognitive load warnings
        if result.cognitive_load and result.cognitive_load.warnings:
            warnings.extend(result.cognitive_load.warnings[:3])
        
        # Role balance warnings
        if result.explanatory_balance:
            bal = result.explanatory_balance
            if bal.define_status == "insufficient":
                warnings.append("Insufficient definition blocks")
            if bal.explain_status == "insufficient":
                warnings.append("Insufficient explanation blocks")
            if bal.implement_status == "dominant":
                warnings.append("Implementation blocks dominate context")
        
        return warnings[:5]  # Cap at 5


def format_level3_diagnostic(result: Level3DiagnosticResult) -> str:
    """Format Level-3 diagnostic for terminal output."""
    lines = []
    
    lines.append("[LEVEL-3 CONTEXT DIAGNOSTIC]")
    
    # Intent coverage
    lines.append(f"Intent Coverage: {result.intent_coverage_score:.0%}")
    
    # Missing concepts
    if result.missing_concepts:
        lines.append("Missing Concepts:")
        for concept in result.missing_concepts[:5]:
            lines.append(f"  - {concept}")
    
    # Explanatory balance
    if result.explanatory_balance:
        bal = result.explanatory_balance
        lines.append("Explanatory Balance:")
        lines.append(f"  DEFINE: {bal.define_status} ({bal.define_count})")
        lines.append(f"  IMPLEMENT: {bal.implement_status} ({bal.implement_count})")
        lines.append(f"  EXPLAIN: {bal.explain_status} ({bal.explain_count})")
    
    # Cognitive load
    if result.cognitive_load:
        load = result.cognitive_load
        lines.append("Cognitive Load:")
        lines.append(f"  {load.overall_load.value} ({load.high_load_count} blocks exceed threshold)")
    
    # Primary failure mode
    lines.append(f"Primary Failure Mode:")
    lines.append(f"  {result.primary_failure_mode.value}")
    
    # Warnings
    if result.warnings:
        lines.append("Warnings:")
        for warning in result.warnings:
            lines.append(f"! {warning}")
    
    return "\n".join(lines)


def format_level3_json(result: Level3DiagnosticResult) -> dict:
    """Format Level-3 diagnostic as JSON-serializable dict."""
    return {
        "intent_coverage_score": result.intent_coverage_score,
        "explanation_completeness": result.explanation_completeness,
        "missing_concepts": result.missing_concepts,
        "explanatory_balance": {
            "define": result.explanatory_balance.define_count if result.explanatory_balance else 0,
            "implement": result.explanatory_balance.implement_count if result.explanatory_balance else 0,
            "explain": result.explanatory_balance.explain_count if result.explanatory_balance else 0,
            "noise": result.explanatory_balance.noise_count if result.explanatory_balance else 0,
        },
        "cognitive_load": {
            "level": result.cognitive_load.overall_load.value if result.cognitive_load else "N/A",
            "high_count": result.cognitive_load.high_load_count if result.cognitive_load else 0,
        },
        "primary_failure_mode": result.primary_failure_mode.value,
        "warnings": result.warnings,
    }


def format_level3_markdown(result: Level3DiagnosticResult) -> str:
    """Format Level-3 diagnostic as Markdown."""
    lines = []
    
    lines.append("## Level-3 Context Cognitive Diagnostic")
    lines.append("")
    
    # Summary table
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Intent Coverage | {result.intent_coverage_score:.0%} |")
    lines.append(f"| Explanation Completeness | {result.explanation_completeness:.0%} |")
    
    if result.cognitive_load:
        lines.append(f"| Cognitive Load | {result.cognitive_load.overall_load.value} |")
    
    lines.append(f"| Primary Failure Mode | {result.primary_failure_mode.value} |")
    lines.append("")
    
    # Missing concepts
    if result.missing_concepts:
        lines.append("### Missing Concepts")
        for concept in result.missing_concepts:
            lines.append(f"- `{concept}`")
        lines.append("")
    
    # Warnings
    if result.warnings:
        lines.append("### Warnings")
        for warning in result.warnings:
            lines.append(f"- {warning}")
    
    return "\n".join(lines)


# =============================================================================
# DEMO
# =============================================================================

def demo_level3_analysis() -> str:
    """Demo function with sample data."""
    from diagnostics.context.inspect_context import (
        TokenBreakdown,
        IdentifierDensity,
        StructuralPayload,
        RedundancyHints,
    )
    
    # Create sample blocks
    blocks = [
        IntraBlockDiagnostic(
            block_id="QueryOptimizer.optimize",
            file="query_optimizer.py",
            symbol="QueryOptimizer.optimize",
            tokens=400,
            token_breakdown=TokenBreakdown(
                code_logic_pct=45,
                control_flow_pct=15,
                docstrings_pct=10,
            ),
            identifier_density=IdentifierDensity(
                total_unique=20,
                top_repeated=[("query", 5), ("rules", 4)],
                density_ratio=0.4,
            ),
            structural_payload=StructuralPayload(
                method_count=1,
                nested_depth_max=2,
            ),
            redundancy_hints=RedundancyHints(),
            signal_ratio=0.6,
            noise_ratio=0.2,
        ),
        IntraBlockDiagnostic(
            block_id="Rule.apply",
            file="rules.py",
            symbol="Rule.apply",
            tokens=200,
            token_breakdown=TokenBreakdown(
                code_logic_pct=50,
                control_flow_pct=10,
            ),
            identifier_density=IdentifierDensity(
                total_unique=10,
                top_repeated=[("rule", 3)],
                density_ratio=0.3,
            ),
            structural_payload=StructuralPayload(
                method_count=1,
                nested_depth_max=1,
            ),
            redundancy_hints=RedundancyHints(),
            signal_ratio=0.7,
            noise_ratio=0.15,
        ),
    ]
    
    query = "How does the QueryOptimizer resolve conflicting rules?"
    
    analyzer = AlignmentSummaryAnalyzer()
    result = analyzer.analyze(query, blocks)
    
    return format_level3_diagnostic(result)
