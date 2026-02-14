"""
Diagnostic Controller

Concrete implementation of DiagnosticProvider that orchestrates
L1, L2, and L3 diagnostics to produce DiagnosticSnapshots.

This controller:
- Knows where diagnostics live
- Does NOT know who uses them
- Does NOT make decisions or optimizations
- Does NOT mutate any state
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from homllm.context.interfaces import ContextArtifact, ContextBlock

from homllm.intelligence.interfaces import (
    DiagnosticSnapshot,
    StructuralDiagnostics,
    SemanticDiagnostics,
    CognitiveDiagnostics,
    IntraBlockDiagnostic,
    ContextDiagnosticResult,
    RelationalDiagnosticResult,
    Level3DiagnosticResult,
)

# L1 diagnostics
from homllm.intelligence.diagnostics.inspect_context import (
    BlockContentAnalyzer,
    ContextBlockInfo,
)

# L2 diagnostics
from homllm.intelligence.diagnostics.inspect_context_relations import (
    ContextRelationDiagnostics,
)

# L3 diagnostics
from homllm.intelligence.diagnostics.context_level3.inspect_alignment_summary import (
    AlignmentSummaryAnalyzer,
)


class DiagnosticController:
    """
    Concrete implementation of DiagnosticProvider.
    
    Orchestrates L1, L2, L3 diagnostics without embedding any
    decision logic. Wraps diagnostic outputs into typed containers.
    
    Usage:
        controller = DiagnosticController()
        snapshot = controller.analyze(context_artifact)
    
    Guarantees:
    - No side effects (no logging, printing, IO in analyze path)
    - No mutations to context
    - Deterministic output
    - Explicit failure representation
    """
    
    def __init__(
        self,
        source_root: Optional[Path] = None,
        similarity_threshold: float = 0.3,
        cluster_threshold: float = 0.5,
    ):
        """
        Initialize the diagnostic controller.
        
        Args:
            source_root: Optional root path for reading source files.
                         If None, uses block content directly.
            similarity_threshold: Threshold for L2 similarity analysis
            cluster_threshold: Threshold for L2 redundancy clustering
        """
        self._source_root = source_root
        
        # L1 analyzer (stateless)
        self._block_analyzer = BlockContentAnalyzer()
        
        # L2 analyzer (stateless)
        self._relation_analyzer = ContextRelationDiagnostics(
            similarity_threshold=similarity_threshold,
            cluster_threshold=cluster_threshold,
        )
        
        # L3 analyzer (stateless)
        self._alignment_analyzer = AlignmentSummaryAnalyzer()
    
    def analyze(self, context: ContextArtifact) -> DiagnosticSnapshot:
        """
        Analyze a context artifact and produce a diagnostic snapshot.
        
        This method orchestrates all three diagnostic levels:
        1. L1: Structural diagnostics (per-block analysis)
        2. L2: Semantic diagnostics (relational analysis)
        3. L3: Cognitive diagnostics (alignment analysis)
        
        Args:
            context: ContextArtifact to analyze
            
        Returns:
            DiagnosticSnapshot with all levels populated.
            Failed levels have status="unavailable" with reason.
        """
        # Run L1 diagnostics
        level1 = self._run_level1(context)
        
        # Run L2 diagnostics (requires L1 blocks)
        level2 = self._run_level2(level1)
        
        # Run L3 diagnostics (requires L1 blocks and query)
        level3 = self._run_level3(context, level1)
        
        return DiagnosticSnapshot(
            level1=level1,
            level2=level2,
            level3=level3,
        )
    
    def _run_level1(self, context: ContextArtifact) -> StructuralDiagnostics:
        """
        Run Level-1 structural diagnostics.
        
        Analyzes each block for:
        - Token breakdown (code logic, comments, logging, etc.)
        - Identifier density
        - Structural payload (functions, classes, methods)
        - Redundancy hints
        - Signal/noise ratios
        """
        try:
            if not context.blocks:
                return StructuralDiagnostics(
                    status="unavailable",
                    reason="No blocks in context",
                    blocks=(),
                    result=None,
                )

            # Prefer token counts produced by the context pipeline (allocated tokens),
            # falling back to cheap estimation when provenance is unavailable.
            token_map: dict[str, int] = {}
            try:
                prov_blocks = (context.provenance or {}).get("blocks", [])
                for entry in prov_blocks:
                    block_id = entry.get("block_id")
                    tokens = entry.get("tokens")
                    if block_id and isinstance(tokens, (int, float)):
                        token_map[str(block_id)] = int(tokens)
            except Exception:
                token_map = {}
            
            # Analyze each block
            intra_blocks: list[IntraBlockDiagnostic] = []
            
            for block in context.blocks:
                diagnostic = self._analyze_block(block, token_count_override=token_map.get(block.block_id))
                intra_blocks.append(diagnostic)
            
            # Build aggregate result
            total_tokens = sum(b.tokens for b in intra_blocks)
            # Align with the context artifact accounting when available.
            if getattr(context, "used_tokens", 0):
                total_tokens = int(context.used_tokens)
            
            result = ContextDiagnosticResult(
                query_id=context.query_id,
                run_id=None,
                total_blocks=len(intra_blocks),
                total_tokens=total_tokens,
                token_budget=context.token_budget,
                used_budget_pct=(total_tokens / context.token_budget * 100) if context.token_budget > 0 else 0.0,
            )

            # Populate block-level summary for downstream diagnostics consumers.
            block_infos: list[ContextBlockInfo] = []
            for idx, block in enumerate(context.blocks):
                per_block_tokens = token_map.get(block.block_id)
                if per_block_tokens is None:
                    # Fall back to the analyzer's accounting (heuristic) rather than lying.
                    per_block_tokens = intra_blocks[idx].tokens if idx < len(intra_blocks) else 0

                block_infos.append(
                    ContextBlockInfo(
                        block_id=block.block_id,
                        file=block.file,
                        start_line=block.start_line,
                        end_line=block.end_line,
                        tokens=int(per_block_tokens),
                        provenance=tuple(block.provenance),
                        position=idx,
                    )
                )
            result.blocks = block_infos

            # Derived signals (reusing the semantics from ContextDiagnostics).
            if result.blocks and result.total_tokens > 0:
                sorted_blocks = sorted(result.blocks, key=lambda b: b.tokens, reverse=True)
                top_k = 5
                top_tokens = sum(b.tokens for b in sorted_blocks[:top_k])
                result.top_k_token_concentration = (top_tokens / result.total_tokens) * 100

                # Simple redundancy signal: many blocks from the same file.
                file_groups: dict[str, list[ContextBlockInfo]] = {}
                for bi in result.blocks:
                    file_groups.setdefault(bi.file, []).append(bi)

                for file, blocks in file_groups.items():
                    if len(blocks) >= 3:
                        result.redundant_blocks.append(
                            {
                                "file": file,
                                "block_count": len(blocks),
                                "total_tokens": sum(b.tokens for b in blocks),
                                "lines_covered": (
                                    min(b.start_line for b in blocks),
                                    max(b.end_line for b in blocks),
                                ),
                            }
                        )
                        result.warnings.append(f"Potential redundancy: {len(blocks)} blocks from {file}")

                if result.used_budget_pct > 95:
                    result.warnings.append(f"Near budget limit: {result.used_budget_pct:.1f}% used")
                if result.top_k_token_concentration > 80 and len(result.blocks) > 10:
                    result.warnings.append(
                        f"High token concentration: top {top_k} blocks use {result.top_k_token_concentration:.0f}% of tokens"
                    )
            
            return StructuralDiagnostics(
                status="available",
                reason="",
                blocks=tuple(intra_blocks),
                result=result,
            )
            
        except Exception as e:
            return StructuralDiagnostics(
                status="unavailable",
                reason=f"L1 analysis failed: {type(e).__name__}: {str(e)}",
                blocks=(),
                result=None,
            )
    
    def _run_level2(self, level1: StructuralDiagnostics) -> SemanticDiagnostics:
        """
        Run Level-2 semantic diagnostics.
        
        Analyzes relationships between blocks:
        - Similarity graph
        - Redundancy clusters
        - Concept coverage
        - Dependency chains
        - Narrative flow
        """
        try:
            if level1.status != "available" or not level1.blocks:
                return SemanticDiagnostics(
                    status="unavailable",
                    reason="L2 requires L1 blocks to be available",
                    result=None,
                )
            
            # Run relational analysis on L1 blocks
            result = self._relation_analyzer.analyze(list(level1.blocks))
            
            return SemanticDiagnostics(
                status="available",
                reason="",
                result=result,
            )
            
        except Exception as e:
            return SemanticDiagnostics(
                status="unavailable",
                reason=f"L2 analysis failed: {type(e).__name__}: {str(e)}",
                result=None,
            )
    
    def _run_level3(
        self,
        context: ContextArtifact,
        level1: StructuralDiagnostics,
    ) -> CognitiveDiagnostics:
        """
        Run Level-3 cognitive diagnostics.
        
        Analyzes cognitive aspects:
        - Query intent decomposition
        - Explanatory role classification
        - Concept coverage gaps
        - Cognitive load estimation
        - Alignment summary
        """
        try:
            if level1.status != "available" or not level1.blocks:
                return CognitiveDiagnostics(
                    status="unavailable",
                    reason="L3 requires L1 blocks to be available",
                    result=None,
                )
            
            # Extract query from context (use query_id as fallback)
            query = self._extract_query(context)
            
            if not query:
                return CognitiveDiagnostics(
                    status="unavailable",
                    reason="No query text available for L3 analysis",
                    result=None,
                )
            
            # Build block metadata for concept coverage
            context_blocks: dict[str, dict] = {}
            try:
                for block in context.blocks:
                    context_blocks[block.block_id] = {
                        "file": block.file,
                        "preview": (block.content or "")[:300],
                    }
            except Exception:
                context_blocks = {}

            # Run alignment analysis
            result = self._alignment_analyzer.analyze(
                query=query,
                blocks=list(level1.blocks),
                context_blocks=context_blocks,
            )
            
            return CognitiveDiagnostics(
                status="available",
                reason="",
                result=result,
            )
            
        except Exception as e:
            return CognitiveDiagnostics(
                status="unavailable",
                reason=f"L3 analysis failed: {type(e).__name__}: {str(e)}",
                result=None,
            )
    
    def _analyze_block(
        self,
        block: ContextBlock,
        token_count_override: int | None = None,
    ) -> IntraBlockDiagnostic:
        """
        Analyze a single context block.
        
        Uses BlockContentAnalyzer to produce IntraBlockDiagnostic.
        """
        # Prefer context pipeline token accounting when available.
        if token_count_override is not None:
            token_count = max(1, int(token_count_override))
        else:
            # Estimate tokens from content (cheap, deterministic)
            token_count = max(1, len(block.content.split()) // 2)
        
        return self._block_analyzer.analyze(
            content=block.content,
            block_id=block.block_id,
            file=block.file,
            symbol=block.symbol_name or block.symbol_id or "",
            token_count=token_count,
        )
    
    def _extract_query(self, context: ContextArtifact) -> str:
        """
        Extract query text from context artifact.
        
        Tries to find query in provenance, falls back to query_id.
        """
        # Check provenance for query text
        if context.provenance:
            query = context.provenance.get("query", "")
            if query:
                return str(query)
            
            query = context.provenance.get("query_text", "")
            if query:
                return str(query)
        
        # Fallback to query_id (may be the actual query in some cases)
        if context.query_id and not context.query_id.startswith("run_"):
            return str(context.query_id)
        
        return ""


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_diagnostic_provider(
    source_root: Optional[Path] = None,
    similarity_threshold: float = 0.3,
    cluster_threshold: float = 0.5,
) -> DiagnosticController:
    """
    Factory function to create a DiagnosticProvider implementation.
    
    Args:
        source_root: Optional root path for source files
        similarity_threshold: L2 similarity threshold
        cluster_threshold: L2 cluster threshold
        
    Returns:
        DiagnosticController instance
    """
    return DiagnosticController(
        source_root=source_root,
        similarity_threshold=similarity_threshold,
        cluster_threshold=cluster_threshold,
    )


__all__ = [
    "DiagnosticController",
    "create_diagnostic_provider",
]
