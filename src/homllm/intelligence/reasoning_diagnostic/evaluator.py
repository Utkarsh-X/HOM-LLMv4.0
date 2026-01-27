"""
Reasoning Diagnostic Evaluator

Evaluates generated answers for reasoning failures:
- Aggregation missing (enumeration expected but not provided)
- Interaction missing (components not connected)
- Premature surrender (claims "not found" despite readable context)

CONSTRAINTS (ABSOLUTE):
- Purely read-only
- Fully deterministic
- No thresholds or fuzzy scoring
- Binary classifications only
- Keyword-based detection
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from homllm.intelligence.reasoning_diagnostic.interfaces import (
    QueryTypeFlag,
    DiagnosticConfidence,
    ReasoningExpectation,
    ReasoningFailure,
    EvidenceSummary,
    ReasoningDiagnosticResult,
)

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact
    from homllm.intelligence.assertion_readability import ReadabilityResult


# =============================================================================
# KEYWORD PATTERNS (DETERMINISTIC, NO FUZZY MATCHING)
# =============================================================================

# Query type detection keywords
ENUMERATIVE_KEYWORDS = frozenset({
    "all", "every", "each", "list", "how many", "enumerate",
    "what are the", "describe the", "name the", "count",
})

INTERACTIONAL_KEYWORDS = frozenset({
    "interact", "combine", "together", "between", "relationship",
    "how do", "how does", "connect", "coordinate", "integrate",
})

TRACE_KEYWORDS = frozenset({
    "trace", "flow", "execution", "step", "sequence", "order",
    "walk through", "path", "chain", "lifecycle",
})

# Answer enumeration markers
ENUMERATION_PATTERNS = [
    r"\b1\.\s",           # "1. "
    r"\b2\.\s",           # "2. "
    r"\bfirst\b",         # "first"
    r"\bsecond\b",        # "second"
    r"\bthird\b",         # "third"
    r"\ball\s+\d+\b",     # "all 5"
    r"\btotal of\b",      # "total of"
    r"\*\*\d+\.",         # "**1."
]

# Answer interaction markers
INTERACTION_PATTERNS = [
    r"\btriggers?\b",      # "triggers"
    r"\bcalls?\b",         # "calls"
    r"\bpasses?\b",        # "passes"
    r"\breturns?\s+to\b",  # "returns to"
    r"\bwhich\s+then\b",   # "which then"
    r"\bafter\s+which\b",  # "after which"
    r"\bbefore\b",         # "before"
    r"\bthen\b",           # "then"
    r"\b→\b",              # arrow
]

# Surrender phrases
SURRENDER_PATTERNS = [
    r"not\s+in\s+context",
    r"not\s+found",
    r"cannot\s+determine",
    r"information\s+not\s+available",
    r"not\s+provided",
    r"not\s+present",
    r"no\s+information",
    r"\[not\s+in\s+context\]",
]


class ReasoningDiagnosticEvaluator:
    """
    Evaluates generated answers for reasoning failures.
    
    All classifications are binary and keyword-based.
    No thresholds, no fuzzy logic, no probabilities.
    """
    
    def evaluate(
        self,
        query_text: str,
        answer_text: str,
        readability_result: "ReadabilityResult",
        context: "ContextArtifact",
    ) -> ReasoningDiagnosticResult:
        """
        Evaluate answer for reasoning failures.
        
        Args:
            query_text: Original query string
            answer_text: Generated answer text
            readability_result: Result from ARM evaluation
            context: Original ContextArtifact
            
        Returns:
            ReasoningDiagnosticResult with classifications.
        """
        query_lower = query_text.lower()
        answer_lower = answer_text.lower()
        
        # Step 1: Detect query type flags
        query_flags = self._detect_query_type(query_lower)
        
        # Step 2: Build expectations from flags
        expectations = ReasoningExpectation(
            aggregation_expected=QueryTypeFlag.ENUMERATIVE in query_flags,
            interaction_expected=QueryTypeFlag.INTERACTIONAL in query_flags,
            trace_expected=QueryTypeFlag.TRACE in query_flags,
        )
        
        # Step 3: Gather evidence from answer
        enumeration_found = self._has_enumeration_markers(answer_lower)
        interaction_found = self._has_interaction_markers(answer_lower)
        surrender_found = self._has_surrender_phrases(answer_lower)
        
        # Step 4: Count readable blocks and components
        readable_blocks = readability_result.readable_count
        distinct_components = self._count_distinct_components(context)
        
        # Step 5: Build evidence summary
        evidence = EvidenceSummary(
            readable_blocks=readable_blocks,
            distinct_components_detected=distinct_components,
            enumeration_markers_found=enumeration_found,
            interaction_markers_found=interaction_found,
            surrender_phrases_found=surrender_found,
        )
        
        # Step 6: Classify failures (binary rules)
        failures = self._classify_failures(
            expectations=expectations,
            readable_blocks=readable_blocks,
            distinct_components=distinct_components,
            enumeration_found=enumeration_found,
            interaction_found=interaction_found,
            surrender_found=surrender_found,
        )
        
        # Step 7: Determine confidence
        confidence = self._determine_confidence(evidence, failures)
        
        return ReasoningDiagnosticResult(
            query_type_flags=tuple(query_flags),
            expectations=expectations,
            failures=failures,
            evidence=evidence,
            confidence=confidence,
        )
    
    def _detect_query_type(self, query_lower: str) -> list[QueryTypeFlag]:
        """Detect query type flags via keyword matching."""
        flags = []
        
        for keyword in ENUMERATIVE_KEYWORDS:
            if keyword in query_lower:
                flags.append(QueryTypeFlag.ENUMERATIVE)
                break
        
        for keyword in INTERACTIONAL_KEYWORDS:
            if keyword in query_lower:
                flags.append(QueryTypeFlag.INTERACTIONAL)
                break
        
        for keyword in TRACE_KEYWORDS:
            if keyword in query_lower:
                flags.append(QueryTypeFlag.TRACE)
                break
        
        return flags
    
    def _has_enumeration_markers(self, answer_lower: str) -> bool:
        """Check if answer contains enumeration markers."""
        for pattern in ENUMERATION_PATTERNS:
            if re.search(pattern, answer_lower, re.IGNORECASE):
                return True
        return False
    
    def _has_interaction_markers(self, answer_lower: str) -> bool:
        """Check if answer contains interaction markers."""
        for pattern in INTERACTION_PATTERNS:
            if re.search(pattern, answer_lower, re.IGNORECASE):
                return True
        return False
    
    def _has_surrender_phrases(self, answer_lower: str) -> bool:
        """Check if answer contains surrender phrases."""
        for pattern in SURRENDER_PATTERNS:
            if re.search(pattern, answer_lower, re.IGNORECASE):
                return True
        return False
    
    def _count_distinct_components(self, context: "ContextArtifact") -> int:
        """Count distinct components (files/symbols) in context."""
        if not context.blocks:
            return 0
        
        # Count unique files as proxy for distinct components
        unique_files = set()
        for block in context.blocks:
            unique_files.add(block.file)
        
        return len(unique_files)
    
    def _classify_failures(
        self,
        expectations: ReasoningExpectation,
        readable_blocks: int,
        distinct_components: int,
        enumeration_found: bool,
        interaction_found: bool,
        surrender_found: bool,
    ) -> ReasoningFailure:
        """
        Classify reasoning failures using binary rules.
        
        NO thresholds. NO fuzzy logic. Binary conditions only.
        """
        # Aggregation Missing:
        # TRUE if: aggregation expected AND readable blocks >= 2 AND no enumeration
        aggregation_missing = (
            expectations.aggregation_expected
            and readable_blocks >= 2
            and not enumeration_found
        )
        
        # Interaction Missing:
        # TRUE if: distinct components >= 2 AND no interaction markers
        interaction_missing = (
            distinct_components >= 2
            and not interaction_found
        )
        
        # Premature Surrender:
        # TRUE if: surrender phrases found AND readable blocks > 0
        premature_surrender = (
            surrender_found
            and readable_blocks > 0
        )
        
        return ReasoningFailure(
            aggregation_missing=aggregation_missing,
            interaction_missing=interaction_missing,
            premature_surrender=premature_surrender,
        )
    
    def _determine_confidence(
        self,
        evidence: EvidenceSummary,
        failures: ReasoningFailure,
    ) -> DiagnosticConfidence:
        """
        Determine confidence based on evidence count.
        
        NOT probability — just evidence presence.
        """
        failure_count = sum([
            failures.aggregation_missing,
            failures.interaction_missing,
            failures.premature_surrender,
        ])
        
        evidence_count = sum([
            evidence.readable_blocks > 0,
            evidence.distinct_components_detected >= 2,
            evidence.enumeration_markers_found,
            evidence.interaction_markers_found,
            evidence.surrender_phrases_found,
        ])
        
        if failure_count >= 2 or (failure_count >= 1 and evidence_count >= 3):
            return DiagnosticConfidence.STRONG
        elif failure_count >= 1 or evidence_count >= 2:
            return DiagnosticConfidence.MODERATE
        else:
            return DiagnosticConfidence.WEAK


def create_reasoning_evaluator() -> ReasoningDiagnosticEvaluator:
    """Factory function to create evaluator."""
    return ReasoningDiagnosticEvaluator()


__all__ = [
    "ReasoningDiagnosticEvaluator",
    "create_reasoning_evaluator",
]
