"""
Level-2 Context Diagnostics: Relational Intelligence Layer

Analyzes relationships between context blocks, not individual blocks.
Explains why blocks are redundant, dominant, missing, or badly ordered.

CONSTRAINTS (ABSOLUTE):
- No mutation of core HOM-LLM logic
- No imports that affect runtime behavior
- No feedback into retrieval, ranking, or context selection
- No LLM usage (no prompts, no generation)
- No ML models
- Read-only analysis only
- Deterministic and replayable

Read-only: Never modifies core system artifacts.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from collections import Counter
import re

from diagnostics.common.utils import safe_divide
from diagnostics.context.inspect_context import (
    IntraBlockDiagnostic,
    ContextBlockInfo,
)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class SimilarityEdge:
    """Edge in similarity graph between two blocks."""
    block_a_id: str
    block_b_id: str
    score: float  # 0.0 to 1.0
    signals: dict[str, float] = field(default_factory=dict)


@dataclass
class RedundancyCluster:
    """A cluster of redundant blocks."""
    cluster_id: int
    block_ids: list[str]
    total_tokens: int
    dominant_block_id: str  # Highest signal ratio
    dominant_signal_ratio: float
    token_pct: float = 0.0  # Percentage of total context tokens


@dataclass
class ConceptCoverage:
    """Coverage of a concept across blocks."""
    concept: str
    block_ids: list[str]
    token_weight: int
    coverage_pct: float


@dataclass
class DependencyAnalysis:
    """Dependency chain analysis results."""
    max_depth: int
    root_blocks: list[str]  # No incoming dependencies
    leaf_blocks: list[str]  # No outgoing dependencies
    orphan_blocks: list[str]  # No dependencies at all
    edges: list[tuple[str, str]]  # (from, to) pairs


@dataclass
class NarrativeFlowResult:
    """Narrative flow analysis results."""
    score: str  # HIGH, MEDIUM, LOW
    explanation: str
    violations: list[str]  # Specific ordering violations


@dataclass
class RelationalDiagnosticResult:
    """Complete Level-2 diagnostic result."""
    
    # Similarity graph (internal, not output directly)
    similarity_edges: list[SimilarityEdge] = field(default_factory=list)
    
    # Redundancy clusters
    redundancy_clusters: list[RedundancyCluster] = field(default_factory=list)
    largest_cluster_token_pct: float = 0.0
    dominant_block_id: str = ""
    
    # Concept coverage
    concept_coverage: list[ConceptCoverage] = field(default_factory=list)
    
    # Dependency analysis
    dependency_analysis: Optional[DependencyAnalysis] = None
    
    # Narrative flow
    narrative_flow: Optional[NarrativeFlowResult] = None
    
    # Warnings
    warnings: list[str] = field(default_factory=list)


# =============================================================================
# BLOCK SIMILARITY GRAPH (Analysis 1)
# =============================================================================

class SimilarityAnalyzer:
    """
    Builds similarity graph across context blocks.
    
    Similarity signals (deterministic combination):
    - Identifier overlap ratio (40%)
    - File proximity (30%)
    - Structural similarity (30%)
    """
    
    IDENTIFIER_WEIGHT = 0.4
    FILE_PROXIMITY_WEIGHT = 0.3
    STRUCTURAL_WEIGHT = 0.3
    
    def __init__(self, threshold: float = 0.3):
        """
        Args:
            threshold: Minimum similarity to create an edge
        """
        self.threshold = threshold
    
    def build_graph(
        self, 
        blocks: list[IntraBlockDiagnostic]
    ) -> list[SimilarityEdge]:
        """
        Build similarity graph with O(n²) pairwise comparison.
        
        Args:
            blocks: List of Level-1 diagnostics
            
        Returns:
            List of similarity edges above threshold
        """
        edges = []
        n = len(blocks)
        
        for i in range(n):
            for j in range(i + 1, n):
                block_a = blocks[i]
                block_b = blocks[j]
                
                signals = self._compute_signals(block_a, block_b)
                score = self._combine_signals(signals)
                
                if score >= self.threshold:
                    edges.append(SimilarityEdge(
                        block_a_id=block_a.block_id,
                        block_b_id=block_b.block_id,
                        score=score,
                        signals=signals,
                    ))
        
        return edges
    
    def _compute_signals(
        self,
        block_a: IntraBlockDiagnostic,
        block_b: IntraBlockDiagnostic
    ) -> dict[str, float]:
        """Compute individual similarity signals."""
        signals = {}
        
        # 1. Identifier overlap ratio (Jaccard)
        ids_a = set(ident for ident, _ in block_a.identifier_density.top_repeated)
        ids_b = set(ident for ident, _ in block_b.identifier_density.top_repeated)
        
        if ids_a or ids_b:
            intersection = len(ids_a & ids_b)
            union = len(ids_a | ids_b)
            signals["identifier_overlap"] = safe_divide(intersection, union, 0.0)
        else:
            signals["identifier_overlap"] = 0.0
        
        # 2. File proximity
        file_a = Path(block_a.file)
        file_b = Path(block_b.file)
        
        if file_a == file_b:
            signals["file_proximity"] = 1.0
        elif file_a.parent == file_b.parent:
            signals["file_proximity"] = 0.7
        elif len(set(file_a.parts) & set(file_b.parts)) > 1:
            signals["file_proximity"] = 0.3
        else:
            signals["file_proximity"] = 0.0
        
        # 3. Structural similarity
        struct_a = block_a.structural_payload
        struct_b = block_b.structural_payload
        
        # Same type of content?
        type_match = 0.0
        if struct_a.function_count > 0 and struct_b.function_count > 0:
            type_match = 0.5
        elif struct_a.class_count > 0 and struct_b.class_count > 0:
            type_match = 0.5
        elif struct_a.method_count > 0 and struct_b.method_count > 0:
            type_match = 0.5
        
        # Similar size?
        size_a = block_a.tokens
        size_b = block_b.tokens
        size_ratio = safe_divide(min(size_a, size_b), max(size_a, size_b), 0.0)
        
        signals["structural_similarity"] = (type_match + size_ratio * 0.5)
        
        return signals
    
    def _combine_signals(self, signals: dict[str, float]) -> float:
        """Combine signals into final similarity score."""
        score = (
            signals.get("identifier_overlap", 0.0) * self.IDENTIFIER_WEIGHT +
            signals.get("file_proximity", 0.0) * self.FILE_PROXIMITY_WEIGHT +
            signals.get("structural_similarity", 0.0) * self.STRUCTURAL_WEIGHT
        )
        return min(1.0, max(0.0, score))


# =============================================================================
# REDUNDANCY CLUSTER DETECTION (Analysis 2)
# =============================================================================

class RedundancyClusterAnalyzer:
    """
    Groups blocks into redundancy clusters using Union-Find.
    """
    
    def __init__(self, similarity_threshold: float = 0.5):
        self.similarity_threshold = similarity_threshold
    
    def find_clusters(
        self,
        blocks: list[IntraBlockDiagnostic],
        edges: list[SimilarityEdge],
        total_tokens: int
    ) -> list[RedundancyCluster]:
        """
        Find redundancy clusters using Union-Find.
        
        Args:
            blocks: Level-1 diagnostics
            edges: Similarity edges
            total_tokens: Total context tokens
            
        Returns:
            List of redundancy clusters
        """
        # Build block lookup
        block_map = {b.block_id: b for b in blocks}
        block_ids = list(block_map.keys())
        
        # Union-Find
        parent = {bid: bid for bid in block_ids}
        
        def find(x: str) -> str:
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]
        
        def union(a: str, b: str) -> None:
            pa, pb = find(a), find(b)
            if pa != pb:
                parent[pa] = pb
        
        # Union similar blocks
        for edge in edges:
            if edge.score >= self.similarity_threshold:
                union(edge.block_a_id, edge.block_b_id)
        
        # Group by root
        clusters_map: dict[str, list[str]] = {}
        for bid in block_ids:
            root = find(bid)
            if root not in clusters_map:
                clusters_map[root] = []
            clusters_map[root].append(bid)
        
        # Build cluster objects
        clusters = []
        for cluster_id, (root, members) in enumerate(clusters_map.items()):
            if len(members) < 2:
                continue  # Single-block clusters aren't redundant
            
            # Calculate tokens
            cluster_tokens = sum(block_map[bid].tokens for bid in members)
            
            # Find dominant block (highest signal ratio)
            dominant = max(members, key=lambda bid: block_map[bid].signal_ratio)
            
            clusters.append(RedundancyCluster(
                cluster_id=cluster_id,
                block_ids=members,
                total_tokens=cluster_tokens,
                dominant_block_id=dominant,
                dominant_signal_ratio=block_map[dominant].signal_ratio,
                token_pct=safe_divide(cluster_tokens, total_tokens, 0.0) * 100,
            ))
        
        # Sort by token weight descending
        clusters.sort(key=lambda c: c.total_tokens, reverse=True)
        
        return clusters


# =============================================================================
# CONTEXT COVERAGE MAP (Analysis 3)
# =============================================================================

class CoverageAnalyzer:
    """
    Extracts and groups concepts across blocks.
    """
    
    # Pattern for extracting concepts from identifiers
    CONCEPT_PATTERN = re.compile(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|\d+')
    
    def analyze_coverage(
        self,
        blocks: list[IntraBlockDiagnostic],
        total_tokens: int
    ) -> list[ConceptCoverage]:
        """
        Analyze concept coverage across blocks.
        
        Args:
            blocks: Level-1 diagnostics
            total_tokens: Total context tokens
            
        Returns:
            List of concept coverages, sorted by token weight
        """
        concept_blocks: dict[str, list[str]] = {}
        concept_tokens: dict[str, int] = {}
        
        for block in blocks:
            # Extract concepts from file, symbol, and top identifiers
            concepts = self._extract_concepts(block)
            
            for concept in concepts:
                if concept not in concept_blocks:
                    concept_blocks[concept] = []
                    concept_tokens[concept] = 0
                
                if block.block_id not in concept_blocks[concept]:
                    concept_blocks[concept].append(block.block_id)
                    concept_tokens[concept] += block.tokens
        
        # Build coverage list
        coverages = []
        for concept, block_ids in concept_blocks.items():
            tokens = concept_tokens[concept]
            coverages.append(ConceptCoverage(
                concept=concept,
                block_ids=block_ids,
                token_weight=tokens,
                coverage_pct=safe_divide(tokens, total_tokens, 0.0) * 100,
            ))
        
        # Sort by token weight descending
        coverages.sort(key=lambda c: c.token_weight, reverse=True)
        
        return coverages[:20]  # Top 20 concepts
    
    def _extract_concepts(self, block: IntraBlockDiagnostic) -> set[str]:
        """Extract concepts from a block."""
        concepts = set()
        
        # From file path
        file_parts = Path(block.file).stem.lower().split('_')
        concepts.update(p for p in file_parts if len(p) > 2)
        
        # From symbol
        if block.symbol:
            symbol_parts = self.CONCEPT_PATTERN.findall(block.symbol)
            concepts.update(p.lower() for p in symbol_parts if len(p) > 2)
        
        # From top identifiers
        for ident, _ in block.identifier_density.top_repeated[:5]:
            ident_parts = self.CONCEPT_PATTERN.findall(ident)
            concepts.update(p.lower() for p in ident_parts if len(p) > 2)
        
        return concepts


# =============================================================================
# DEPENDENCY CHAIN ANALYSIS (Analysis 4)
# =============================================================================

class DependencyAnalyzer:
    """
    Detects block dependencies via call/reference relationships.
    """
    
    def analyze_dependencies(
        self,
        blocks: list[IntraBlockDiagnostic]
    ) -> DependencyAnalysis:
        """
        Analyze dependency chains between blocks.
        
        Heuristic: If block A's identifiers appear in block B's symbol,
        B may depend on A.
        
        Args:
            blocks: Level-1 diagnostics
            
        Returns:
            Dependency analysis results
        """
        block_map = {b.block_id: b for b in blocks}
        edges: list[tuple[str, str]] = []
        
        # Build dependency edges
        for block_a in blocks:
            # Get identifiers defined in block A
            symbol_a = block_a.symbol.lower() if block_a.symbol else ""
            
            for block_b in blocks:
                if block_a.block_id == block_b.block_id:
                    continue
                
                # Check if block B's identifiers reference block A's symbol
                for ident, _ in block_b.identifier_density.top_repeated:
                    if symbol_a and ident.lower() in symbol_a:
                        edges.append((block_a.block_id, block_b.block_id))
                        break
        
        # Analyze graph structure
        outgoing: dict[str, set[str]] = {b.block_id: set() for b in blocks}
        incoming: dict[str, set[str]] = {b.block_id: set() for b in blocks}
        
        for src, dst in edges:
            outgoing[src].add(dst)
            incoming[dst].add(src)
        
        # Find roots (no incoming), leaves (no outgoing), orphans (neither)
        roots = [bid for bid in block_map if not incoming[bid] and outgoing[bid]]
        leaves = [bid for bid in block_map if not outgoing[bid] and incoming[bid]]
        orphans = [bid for bid in block_map if not incoming[bid] and not outgoing[bid]]
        
        # Calculate max depth via BFS from roots
        max_depth = self._calculate_max_depth(roots, outgoing)
        
        return DependencyAnalysis(
            max_depth=max_depth,
            root_blocks=roots,
            leaf_blocks=leaves,
            orphan_blocks=orphans,
            edges=edges,
        )
    
    def _calculate_max_depth(
        self,
        roots: list[str],
        outgoing: dict[str, set[str]]
    ) -> int:
        """Calculate maximum dependency depth via BFS."""
        if not roots:
            return 0
        
        max_depth = 0
        visited = set()
        
        for root in roots:
            queue = [(root, 1)]
            while queue:
                node, depth = queue.pop(0)
                if node in visited:
                    continue
                visited.add(node)
                max_depth = max(max_depth, depth)
                
                for child in outgoing.get(node, []):
                    if child not in visited:
                        queue.append((child, depth + 1))
        
        return max_depth


# =============================================================================
# NARRATIVE FLOW HEURISTIC (Analysis 5)
# =============================================================================

class NarrativeFlowAnalyzer:
    """
    Evaluates ordering quality of context blocks.
    
    Good narrative flow:
    - Definitions before usage
    - Classes before methods
    - Public API before internals
    - Caller before callee
    """
    
    def analyze_flow(
        self,
        blocks: list[IntraBlockDiagnostic],
        dependency_analysis: DependencyAnalysis
    ) -> NarrativeFlowResult:
        """
        Analyze narrative flow quality.
        
        Args:
            blocks: Level-1 diagnostics (in context order)
            dependency_analysis: Dependency analysis results
            
        Returns:
            Narrative flow result with score and explanation
        """
        violations = []
        block_positions = {b.block_id: i for i, b in enumerate(blocks)}
        
        # Check 1: Dependencies should come before dependents
        dependency_violations = 0
        for src, dst in dependency_analysis.edges:
            if src in block_positions and dst in block_positions:
                if block_positions[src] > block_positions[dst]:
                    dependency_violations += 1
                    violations.append(f"Definition '{src}' appears after usage in '{dst}'")
        
        # Check 2: Classes should appear before their methods
        class_method_violations = 0
        class_blocks = [b for b in blocks if b.structural_payload.class_count > 0]
        method_blocks = [b for b in blocks if b.structural_payload.method_count > 0]
        
        for cls in class_blocks:
            cls_pos = block_positions[cls.block_id]
            for method in method_blocks:
                if method.file == cls.file:  # Same file = likely related
                    method_pos = block_positions[method.block_id]
                    if method_pos < cls_pos:
                        class_method_violations += 1
                        violations.append(f"Method block appears before class definition")
                        break
        
        # Check 3: Root blocks should appear early
        root_position_violations = 0
        mid_point = len(blocks) // 2
        for root in dependency_analysis.root_blocks:
            if root in block_positions:
                if block_positions[root] > mid_point:
                    root_position_violations += 1
                    violations.append(f"Root block '{root}' appears late in context")
        
        # Calculate score
        total_checks = (
            len(dependency_analysis.edges) + 
            len(class_blocks) + 
            len(dependency_analysis.root_blocks)
        )
        total_violations = (
            dependency_violations + 
            class_method_violations + 
            root_position_violations
        )
        
        if total_checks == 0:
            score = "MEDIUM"
            explanation = "No clear dependency structure to evaluate"
        else:
            violation_ratio = safe_divide(total_violations, total_checks, 0.0)
            
            if violation_ratio < 0.2:
                score = "HIGH"
                explanation = "Good ordering: definitions appear before usage"
            elif violation_ratio < 0.5:
                score = "MEDIUM"
                explanation = "Mixed ordering: some definitions after usage"
            else:
                score = "LOW"
                explanation = "Poor ordering: implementation blocks appear before definition blocks"
        
        return NarrativeFlowResult(
            score=score,
            explanation=explanation,
            violations=violations[:5],  # Top 5 violations
        )


# =============================================================================
# MAIN ANALYZER
# =============================================================================

class ContextRelationDiagnostics:
    """
    Level-2 Context Diagnostics: Relational Intelligence Layer.
    
    Analyzes:
    1. Block Similarity Graph
    2. Redundancy Cluster Detection
    3. Context Coverage Map
    4. Dependency Chain Analysis
    5. Narrative Flow Heuristic
    
    Read-only: Never modifies source data.
    """
    
    def __init__(
        self,
        similarity_threshold: float = 0.3,
        cluster_threshold: float = 0.5
    ):
        self.similarity_analyzer = SimilarityAnalyzer(similarity_threshold)
        self.cluster_analyzer = RedundancyClusterAnalyzer(cluster_threshold)
        self.coverage_analyzer = CoverageAnalyzer()
        self.dependency_analyzer = DependencyAnalyzer()
        self.flow_analyzer = NarrativeFlowAnalyzer()
    
    def analyze(
        self,
        blocks: list[IntraBlockDiagnostic]
    ) -> RelationalDiagnosticResult:
        """
        Run all Level-2 analyses on context blocks.
        
        Args:
            blocks: Level-1 diagnostic results for each block
            
        Returns:
            Complete relational diagnostic result
        """
        if not blocks:
            return RelationalDiagnosticResult(
                warnings=["No blocks to analyze"]
            )
        
        total_tokens = sum(b.tokens for b in blocks)
        result = RelationalDiagnosticResult()
        
        # 1. Build similarity graph
        result.similarity_edges = self.similarity_analyzer.build_graph(blocks)
        
        # 2. Find redundancy clusters
        result.redundancy_clusters = self.cluster_analyzer.find_clusters(
            blocks, result.similarity_edges, total_tokens
        )
        
        if result.redundancy_clusters:
            largest = result.redundancy_clusters[0]
            result.largest_cluster_token_pct = largest.token_pct
            result.dominant_block_id = largest.dominant_block_id
        
        # 3. Analyze concept coverage
        result.concept_coverage = self.coverage_analyzer.analyze_coverage(
            blocks, total_tokens
        )
        
        # 4. Analyze dependencies
        result.dependency_analysis = self.dependency_analyzer.analyze_dependencies(
            blocks
        )
        
        # 5. Analyze narrative flow
        result.narrative_flow = self.flow_analyzer.analyze_flow(
            blocks, result.dependency_analysis
        )
        
        # Generate warnings
        result.warnings = self._generate_warnings(result, total_tokens)
        
        return result
    
    def _generate_warnings(
        self,
        result: RelationalDiagnosticResult,
        total_tokens: int
    ) -> list[str]:
        """Generate warnings based on analysis results."""
        warnings = []
        
        # Redundancy warnings
        if result.largest_cluster_token_pct > 40:
            warnings.append(
                f"High redundancy concentration: {result.largest_cluster_token_pct:.0f}% in largest cluster"
            )
        
        if len(result.redundancy_clusters) >= 3:
            warnings.append(
                f"Multiple redundancy clusters ({len(result.redundancy_clusters)}) competing for budget"
            )
        
        # Coverage warnings
        if result.concept_coverage:
            top_concept = result.concept_coverage[0]
            if top_concept.coverage_pct > 60:
                warnings.append(
                    f"Over-represented concept '{top_concept.concept}': {top_concept.coverage_pct:.0f}%"
                )
        
        # Dependency warnings
        if result.dependency_analysis:
            dep = result.dependency_analysis
            
            if dep.max_depth > 3:
                warnings.append(f"Deep dependency chain: depth {dep.max_depth}")
            
            if not dep.root_blocks and dep.edges:
                warnings.append("Missing explanatory root blocks")
            
            if len(dep.orphan_blocks) > len(dep.root_blocks) + len(dep.leaf_blocks):
                warnings.append(
                    f"Many orphan blocks ({len(dep.orphan_blocks)}): fragmented context"
                )
            
            if dep.leaf_blocks and not dep.root_blocks:
                warnings.append("Leaf-only context: implementation without explanation")
        
        # Narrative flow warnings
        if result.narrative_flow and result.narrative_flow.score == "LOW":
            warnings.append("Poor narrative flow: definitions after usage")
        
        return warnings


# =============================================================================
# OUTPUT FORMATTERS
# =============================================================================

def format_relational_diagnostic(result: RelationalDiagnosticResult) -> str:
    """
    Format relational diagnostic for terminal output.
    
    Matches the specified output format.
    """
    lines = []
    
    lines.append("[CONTEXT RELATIONAL DIAGNOSTIC]")
    
    # Redundancy clusters
    lines.append(f"Redundancy Clusters: {len(result.redundancy_clusters)}")
    lines.append(f"Largest Cluster Tokens: {result.largest_cluster_token_pct:.0f}%")
    if result.dominant_block_id:
        lines.append(f"Dominant Block: {result.dominant_block_id}")
    
    # Dependency analysis
    if result.dependency_analysis:
        dep = result.dependency_analysis
        lines.append(f"Dependency Depth: {dep.max_depth}")
        lines.append(f"Orphan Blocks: {len(dep.orphan_blocks)}")
    
    # Concept coverage
    if result.concept_coverage:
        lines.append("Concept Coverage:")
        for concept in result.concept_coverage[:5]:
            lines.append(f"  - {concept.concept}: {concept.coverage_pct:.0f}%")
    
    # Narrative flow
    if result.narrative_flow:
        lines.append(f"Narrative Flow: {result.narrative_flow.score}")
        lines.append(f"Reason: {result.narrative_flow.explanation}")
    
    # Warnings
    if result.warnings:
        lines.append("Warnings:")
        for warning in result.warnings:
            lines.append(f"! {warning}")
    
    return "\n".join(lines)


def format_relational_diagnostic_json(result: RelationalDiagnosticResult) -> dict:
    """Format relational diagnostic as JSON-serializable dict."""
    dep = result.dependency_analysis
    flow = result.narrative_flow
    
    return {
        "redundancy_clusters": len(result.redundancy_clusters),
        "largest_cluster_token_pct": result.largest_cluster_token_pct,
        "dominant_block": result.dominant_block_id,
        "dependency_depth": dep.max_depth if dep else 0,
        "orphan_blocks": len(dep.orphan_blocks) if dep else 0,
        "root_blocks": len(dep.root_blocks) if dep else 0,
        "leaf_blocks": len(dep.leaf_blocks) if dep else 0,
        "concept_coverage": [
            {"concept": c.concept, "coverage_pct": c.coverage_pct}
            for c in result.concept_coverage[:10]
        ],
        "narrative_flow": {
            "score": flow.score if flow else "N/A",
            "explanation": flow.explanation if flow else "",
        },
        "warnings": result.warnings,
    }


def format_relational_diagnostic_markdown(result: RelationalDiagnosticResult) -> str:
    """Format relational diagnostic as Markdown."""
    lines = []
    
    lines.append("## Context Relational Diagnostic")
    lines.append("")
    
    # Summary table
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Redundancy Clusters | {len(result.redundancy_clusters)} |")
    lines.append(f"| Largest Cluster Tokens | {result.largest_cluster_token_pct:.0f}% |")
    lines.append(f"| Dominant Block | {result.dominant_block_id or 'N/A'} |")
    
    if result.dependency_analysis:
        dep = result.dependency_analysis
        lines.append(f"| Dependency Depth | {dep.max_depth} |")
        lines.append(f"| Orphan Blocks | {len(dep.orphan_blocks)} |")
        lines.append(f"| Root Blocks | {len(dep.root_blocks)} |")
    
    if result.narrative_flow:
        lines.append(f"| Narrative Flow | {result.narrative_flow.score} |")
    
    lines.append("")
    
    # Concept coverage
    if result.concept_coverage:
        lines.append("### Concept Coverage")
        lines.append("")
        for concept in result.concept_coverage[:5]:
            lines.append(f"- **{concept.concept}**: {concept.coverage_pct:.0f}%")
        lines.append("")
    
    # Warnings
    if result.warnings:
        lines.append("### Warnings")
        lines.append("")
        for warning in result.warnings:
            lines.append(f"- {warning}")
    
    return "\n".join(lines)


# =============================================================================
# DEMO
# =============================================================================

def demo_relational_analysis() -> str:
    """
    Demo function with sample blocks.
    """
    from diagnostics.context.inspect_context import (
        TokenBreakdown,
        IdentifierDensity,
        StructuralPayload,
        RedundancyHints,
    )
    
    # Create sample blocks
    blocks = [
        IntraBlockDiagnostic(
            block_id="QueryOptimizer",
            file="query_optimizer.py",
            symbol="QueryOptimizer",
            tokens=400,
            token_breakdown=TokenBreakdown(code_logic_pct=50),
            identifier_density=IdentifierDensity(
                total_unique=20,
                top_repeated=[("query", 5), ("rules", 4), ("optimize", 3)],
            ),
            structural_payload=StructuralPayload(class_count=1),
            redundancy_hints=RedundancyHints(),
            signal_ratio=0.6,
        ),
        IntraBlockDiagnostic(
            block_id="QueryOptimizer.optimize",
            file="query_optimizer.py",
            symbol="QueryOptimizer.optimize",
            tokens=350,
            token_breakdown=TokenBreakdown(code_logic_pct=40),
            identifier_density=IdentifierDensity(
                total_unique=15,
                top_repeated=[("query", 4), ("rules", 3), ("result", 2)],
            ),
            structural_payload=StructuralPayload(method_count=1),
            redundancy_hints=RedundancyHints(),
            signal_ratio=0.5,
        ),
        IntraBlockDiagnostic(
            block_id="Rule.apply",
            file="rules.py",
            symbol="Rule.apply",
            tokens=200,
            token_breakdown=TokenBreakdown(code_logic_pct=60),
            identifier_density=IdentifierDensity(
                total_unique=10,
                top_repeated=[("rule", 3), ("apply", 2)],
            ),
            structural_payload=StructuralPayload(method_count=1),
            redundancy_hints=RedundancyHints(),
            signal_ratio=0.7,
        ),
    ]
    
    analyzer = ContextRelationDiagnostics()
    result = analyzer.analyze(blocks)
    
    return format_relational_diagnostic(result)
