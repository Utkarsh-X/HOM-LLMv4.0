"""
Module 3: Concept Coverage & Gap Detection

Detects missing semantic coverage per query concept.

Per-Concept Analysis:
- Defined? (has DEFINE block)
- Implemented? (has IMPLEMENT block)
- Explained? (has EXPLAIN block)

CONSTRAINTS:
- Deterministic heuristics only
- No ML/LLM
- Read-only
"""

from dataclasses import dataclass, field
from typing import Optional

from diagnostics.context_level3.inspect_query_intent import QueryIntent
from diagnostics.context_level3.inspect_explanatory_roles import (
    BlockRole,
    ExplanatoryRole,
)


@dataclass
class ConceptCoverage:
    """Coverage status for a single concept."""
    
    concept: str
    defined: bool = False
    implemented: bool = False
    explained: bool = False
    
    # Blocks that cover this concept
    define_blocks: list[str] = field(default_factory=list)
    implement_blocks: list[str] = field(default_factory=list)
    explain_blocks: list[str] = field(default_factory=list)
    
    # Coverage score (0-1)
    coverage_score: float = 0.0


@dataclass
class ConceptGapResult:
    """Complete concept gap analysis result."""
    
    # Per-concept coverage
    concept_coverage: list[ConceptCoverage] = field(default_factory=list)
    
    # Summary metrics
    total_concepts: int = 0
    fully_covered: int = 0
    partially_covered: int = 0
    uncovered: int = 0
    
    # Overall coverage score
    overall_coverage_score: float = 0.0
    
    # Warnings
    warnings: list[str] = field(default_factory=list)


class ConceptGapAnalyzer:
    """
    Detects concept coverage gaps between query intent and context blocks.
    
    Cross-references:
    - Query concepts from Module 1
    - Block roles from Module 2
    - Level-2 concept coverage map
    """
    
    def analyze(
        self,
        intent: QueryIntent,
        roles: list[BlockRole],
        block_concepts: Optional[dict[str, list[str]]] = None,
        context_blocks: Optional[dict[str, dict]] = None,
    ) -> ConceptGapResult:
        """
        Analyze concept coverage gaps.
        
        Args:
            intent: Query intent with required concepts
            roles: Block roles from Module 2
            block_concepts: Optional mapping of block_id -> concepts (from Level-2)
            
        Returns:
            ConceptGapResult with coverage analysis
        """
        result = ConceptGapResult()
        
        if not intent.concepts:
            result.warnings.append("No concepts extracted from query")
            return result
        
        # Build concept-to-block mapping
        if block_concepts is None:
            block_concepts = self._extract_block_concepts(roles, context_blocks=context_blocks)
        
        # Analyze each query concept
        for concept in intent.concepts:
            coverage = self._analyze_concept(concept, roles, block_concepts)
            result.concept_coverage.append(coverage)
        
        # Compute summary metrics
        result.total_concepts = len(result.concept_coverage)
        
        for cov in result.concept_coverage:
            if cov.defined and cov.implemented and cov.explained:
                result.fully_covered += 1
            elif cov.defined or cov.implemented or cov.explained:
                result.partially_covered += 1
            else:
                result.uncovered += 1
        
        # Overall score
        total_possible = result.total_concepts * 3  # 3 coverage types
        total_covered = sum(
            (1 if c.defined else 0) + 
            (1 if c.implemented else 0) + 
            (1 if c.explained else 0)
            for c in result.concept_coverage
        )
        result.overall_coverage_score = (
            total_covered / total_possible if total_possible > 0 else 0.0
        )
        
        # Generate warnings
        result.warnings = self._generate_warnings(result)
        
        return result
    
    def _extract_block_concepts(
        self,
        roles: list[BlockRole],
        context_blocks: Optional[dict[str, dict]] = None,
    ) -> dict[str, list[str]]:
        """Extract concepts from block IDs, file paths, and content previews."""
        import re
        
        block_concepts: dict[str, list[str]] = {}
        concept_pattern = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)")
        word_pattern = re.compile(r"\b[A-Za-z0-9_]+\b")
        stopwords = {
            "the", "a", "an", "and", "or", "but", "if", "then", "than",
            "this", "that", "these", "those", "with", "without", "about",
            "into", "from", "to", "of", "for", "in", "on", "at", "by",
            "all", "any", "each", "every", "some", "most", "many", "few",
            "function", "class", "method", "return", "self", "true", "false",
        }
        
        for role in roles:
            parts = concept_pattern.findall(role.block_id)
            concepts = [p.lower() for p in parts if len(p) > 2]
            if context_blocks and role.block_id in context_blocks:
                block_meta = context_blocks[role.block_id]
                file_path = block_meta.get("file") or ""
                preview = block_meta.get("preview") or ""
                for token in word_pattern.findall(file_path):
                    token_lower = token.lower()
                    if len(token_lower) > 2 and token_lower not in stopwords:
                        concepts.append(token_lower)
                for token in word_pattern.findall(preview):
                    token_lower = token.lower()
                    if len(token_lower) > 2 and token_lower not in stopwords:
                        concepts.append(token_lower)
            # Deduplicate while preserving order
            seen = set()
            unique = []
            for c in concepts:
                if c not in seen:
                    seen.add(c)
                    unique.append(c)
            block_concepts[role.block_id] = unique
        
        return block_concepts
    
    def _analyze_concept(
        self,
        concept: str,
        roles: list[BlockRole],
        block_concepts: dict[str, list[str]]
    ) -> ConceptCoverage:
        """Analyze coverage for a single concept."""
        coverage = ConceptCoverage(concept=concept)
        concept_lower = concept.lower()
        
        # Find blocks that mention this concept
        for role in roles:
            block_id = role.block_id
            block_concepts_list = block_concepts.get(block_id, [])
            
            # Check if concept is in block
            if (concept_lower in block_id.lower() or 
                concept_lower in block_concepts_list):
                
                # Categorize by role
                if role.primary_role == ExplanatoryRole.DEFINE:
                    coverage.defined = True
                    coverage.define_blocks.append(block_id)
                
                elif role.primary_role == ExplanatoryRole.IMPLEMENT:
                    coverage.implemented = True
                    coverage.implement_blocks.append(block_id)
                
                elif role.primary_role == ExplanatoryRole.EXPLAIN:
                    coverage.explained = True
                    coverage.explain_blocks.append(block_id)
                
                # Check secondary role too
                if role.secondary_role == ExplanatoryRole.DEFINE:
                    coverage.defined = True
                elif role.secondary_role == ExplanatoryRole.IMPLEMENT:
                    coverage.implemented = True
                elif role.secondary_role == ExplanatoryRole.EXPLAIN:
                    coverage.explained = True
        
        # Compute coverage score
        score = 0.0
        if coverage.defined:
            score += 0.4
        if coverage.implemented:
            score += 0.3
        if coverage.explained:
            score += 0.3
        coverage.coverage_score = score
        
        return coverage
    
    def _generate_warnings(self, result: ConceptGapResult) -> list[str]:
        """Generate warnings based on gaps."""
        warnings = []
        
        for cov in result.concept_coverage:
            if not cov.defined and not cov.implemented and not cov.explained:
                warnings.append(f"Concept '{cov.concept}' has no coverage in context")
            
            elif cov.implemented and not cov.defined:
                warnings.append(
                    f"Concept '{cov.concept}' implemented but not defined"
                )
            
            elif cov.implemented and not cov.explained:
                warnings.append(
                    f"Concept '{cov.concept}' implemented without explanation"
                )
            
            elif cov.explained and not cov.implemented:
                warnings.append(
                    f"Concept '{cov.concept}' explained but not implemented"
                )
        
        if result.uncovered > 0:
            warnings.insert(0, f"{result.uncovered} concept(s) have no coverage")
        
        return warnings


def format_concept_gaps(result: ConceptGapResult) -> str:
    """Format concept gap analysis for display."""
    lines = []
    
    lines.append(f"Concept Coverage: {result.overall_coverage_score:.0%}")
    lines.append(f"  Fully covered: {result.fully_covered}")
    lines.append(f"  Partially covered: {result.partially_covered}")
    lines.append(f"  Uncovered: {result.uncovered}")
    lines.append("")
    
    for cov in result.concept_coverage:
        status = []
        if cov.defined:
            status.append("defined")
        if cov.implemented:
            status.append("implemented")
        if cov.explained:
            status.append("explained")
        
        status_str = ", ".join(status) if status else "MISSING"
        lines.append(f"{cov.concept}:")
        lines.append(f"  status: {status_str}")
    
    return "\n".join(lines)
