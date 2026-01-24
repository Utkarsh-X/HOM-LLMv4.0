"""
Level-2 Semantic Obligation Analyzer

Extracts semantic obligations from diagnostics.
Obligations are requirements that the context must satisfy.

CONSTRAINTS (ABSOLUTE):
- Derives obligations from diagnostics only
- Never invents obligations
- No LLM or ML
- Deterministic
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from homllm.intelligence.actions.level2.plan import SemanticObligation

if TYPE_CHECKING:
    from homllm.intelligence.interfaces import DiagnosticSnapshot
    from homllm.intelligence.diagnostics.context_level3.inspect_query_intent import (
        QueryIntent,
        IntentType,
    )
    from homllm.intelligence.diagnostics.context_level3.inspect_explanatory_roles import (
        BlockRole,
        ExplanatoryRole,
    )


class ObligationAnalyzer:
    """
    Extracts semantic obligations from diagnostics.
    
    Obligation sources:
    1. Query intent concepts → must be covered
    2. Intent type → required explanatory roles
    3. Concept coverage → gaps create obligations
    
    Never guesses. Only diagnostic-derived obligations.
    """
    
    # Mapping from intent type to required roles
    INTENT_ROLE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
        "what": ("DEFINE",),
        "how": ("IMPLEMENT", "EXPLAIN"),
        "why": ("EXPLAIN",),
        "compare": ("DEFINE", "EXPLAIN"),
        "trace": ("IMPLEMENT", "USE"),
        "resolve": ("IMPLEMENT",),
        "unknown": (),
    }
    
    def analyze(
        self,
        diagnostics: DiagnosticSnapshot,
    ) -> tuple[SemanticObligation, ...]:
        """
        Extract all semantic obligations from diagnostics.
        
        Args:
            diagnostics: Complete diagnostic snapshot
            
        Returns:
            Tuple of SemanticObligation objects
        """
        obligations: list[SemanticObligation] = []
        
        # Check L3 availability for query intent
        has_l3 = (
            diagnostics.level3.status == "available" and
            diagnostics.level3.result is not None
        )
        
        if has_l3:
            l3_result = diagnostics.level3.result
            
            # 1. Obligations from query intent concepts
            if l3_result.intent is not None:
                intent_obligations = self._from_query_intent(l3_result.intent)
                obligations.extend(intent_obligations)
            
            # 2. Obligations from concept gaps
            if l3_result.concept_gaps is not None:
                gap_obligations = self._from_concept_gaps(l3_result.concept_gaps)
                obligations.extend(gap_obligations)
            
            # 3. Obligations from block roles balance
            if l3_result.explanatory_balance is not None:
                balance_obligations = self._from_role_balance(l3_result.explanatory_balance)
                obligations.extend(balance_obligations)
        
        return tuple(obligations)
    
    def _from_query_intent(self, intent) -> list[SemanticObligation]:
        """Extract obligations from query intent."""
        obligations = []
        
        # Each concept creates an obligation
        for concept in intent.concepts:
            # Required roles based on intent type
            intent_type_str = intent.intent_type.value if hasattr(intent.intent_type, 'value') else str(intent.intent_type)
            required_roles = self.INTENT_ROLE_REQUIREMENTS.get(intent_type_str, ())
            
            obligations.append(SemanticObligation(
                name=f"cover_{concept}",
                required_concepts=(concept,),
                required_roles=required_roles,
                source="query_intent",
                is_satisfied=False,  # Will be checked later
            ))
        
        # Explanatory intent requires explanation
        if intent.is_explanatory:
            obligations.append(SemanticObligation(
                name="provide_explanation",
                required_concepts=tuple(intent.concepts),
                required_roles=("EXPLAIN",),
                source="query_intent",
                is_satisfied=False,
            ))
        
        # Procedural intent requires implementation
        if intent.is_procedural:
            obligations.append(SemanticObligation(
                name="show_procedure",
                required_concepts=tuple(intent.concepts),
                required_roles=("IMPLEMENT",),
                source="query_intent",
                is_satisfied=False,
            ))
        
        return obligations
    
    def _from_concept_gaps(self, concept_gaps) -> list[SemanticObligation]:
        """Extract obligations from concept gap analysis."""
        obligations = []
        
        for coverage in concept_gaps.concept_coverage:
            # If concept is uncovered, create obligation
            if not coverage.defined and not coverage.implemented and not coverage.explained:
                obligations.append(SemanticObligation(
                    name=f"fill_gap_{coverage.concept}",
                    required_concepts=(coverage.concept,),
                    required_roles=("DEFINE", "EXPLAIN"),
                    source="concept_gaps",
                    is_satisfied=False,
                ))
            
            # Implementation without definition
            elif coverage.implemented and not coverage.defined:
                obligations.append(SemanticObligation(
                    name=f"define_{coverage.concept}",
                    required_concepts=(coverage.concept,),
                    required_roles=("DEFINE",),
                    source="concept_gaps",
                    is_satisfied=False,
                ))
            
            # Implementation without explanation
            elif coverage.implemented and not coverage.explained:
                obligations.append(SemanticObligation(
                    name=f"explain_{coverage.concept}",
                    required_concepts=(coverage.concept,),
                    required_roles=("EXPLAIN",),
                    source="concept_gaps",
                    is_satisfied=False,
                ))
        
        return obligations
    
    def _from_role_balance(self, balance) -> list[SemanticObligation]:
        """Extract obligations from role balance analysis."""
        obligations = []
        
        # Check for role deficiencies
        if hasattr(balance, 'define_status') and balance.define_status != "sufficient":
            obligations.append(SemanticObligation(
                name="need_more_definitions",
                required_concepts=(),
                required_roles=("DEFINE",),
                source="role_balance",
                is_satisfied=False,
            ))
        
        if hasattr(balance, 'explain_status') and balance.explain_status != "sufficient":
            obligations.append(SemanticObligation(
                name="need_more_explanations",
                required_concepts=(),
                required_roles=("EXPLAIN",),
                source="role_balance",
                is_satisfied=False,
            ))
        
        return obligations


__all__ = [
    "ObligationAnalyzer",
]
