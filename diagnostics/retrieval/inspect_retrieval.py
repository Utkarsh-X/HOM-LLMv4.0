"""
Retrieval Diagnostics

Per-query analysis:
- BM25 top-K (ids + scores)
- Vector top-K (ids + scores)
- Overlap count
- Rank correlation

Derived signals:
- Recall overlap %
- Score variance
- Duplicate retrieval detection
- Retrieval dominance (BM25 vs vector)

Read-only: Never modifies core system artifacts.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import json
import statistics

from diagnostics.common.formatters import DiagnosticResult
from diagnostics.common.utils import (
    safe_divide,
    compute_overlap_ratio,
    compute_rank_correlation,
)


@dataclass(frozen=True)
class RetrievalCandidate:
    """A single retrieval candidate with scores."""
    
    doc_id: str
    bm25_score: Optional[float] = None
    vector_score: Optional[float] = None
    merged_score: Optional[float] = None
    provenance: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class RetrievalDiagnosticResult:
    """Complete retrieval diagnostic result."""
    
    query_id: str | int | None
    run_id: str | None
    query_text: str
    
    # Counts
    bm25_count: int = 0
    vector_count: int = 0
    merged_count: int = 0
    
    # Overlap analysis
    overlap_count: int = 0
    overlap_ratio: float = 0.0
    rank_correlation: float = 0.0
    
    # Score distributions
    bm25_score_variance: float = 0.0
    vector_score_variance: float = 0.0
    
    # Dominance
    bm25_dominance_pct: float = 0.0
    vector_dominance_pct: float = 0.0
    
    # Duration
    retrieval_duration_ms: float = 0.0
    
    # Candidates (for detailed analysis)
    bm25_top_k: list[RetrievalCandidate] = field(default_factory=list)
    vector_top_k: list[RetrievalCandidate] = field(default_factory=list)
    
    # Warnings
    warnings: list[str] = field(default_factory=list)


class RetrievalDiagnostics:
    """
    Retrieval diagnostics.
    
    Analyzes BM25 vs vector retrieval to understand:
    - Overlap between methods
    - Which method dominates
    - Score distributions
    - Rank agreement
    
    Read-only: Never modifies source data.
    """
    
    def __init__(self, artifacts_path: Path):
        """
        Initialize retrieval diagnostics.
        
        Args:
            artifacts_path: Path to artifacts directory
        """
        self.artifacts_path = Path(artifacts_path)
        self.runs_path = self.artifacts_path / "runs"
    
    def analyze_run(self, run_id: str, query_text: str = "") -> Optional[RetrievalDiagnosticResult]:
        """
        Analyze retrieval phase for a specific run.
        
        Args:
            run_id: Run ID to analyze
            query_text: Query text (for context)
        
        Returns:
            RetrievalDiagnosticResult or None if run not found
        """
        telemetry_file = self.runs_path / run_id / "telemetry.json"
        if not telemetry_file.exists():
            return None
        
        try:
            with open(telemetry_file, "r", encoding="utf-8") as f:
                telemetry = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
        
        # Extract retrieval phase data
        retrieval_phase = telemetry.get("phases", {}).get("RETRIEVAL", {})
        
        bm25_count = retrieval_phase.get("bm25_count", 0)
        vector_count = retrieval_phase.get("vector_count", 0)
        merged_count = retrieval_phase.get("merged_count", 0)
        duration_ms = retrieval_phase.get("duration_ms", 0.0)
        
        # Build result
        result = RetrievalDiagnosticResult(
            query_id=None,
            run_id=run_id,
            query_text=query_text or telemetry.get("query", ""),
            bm25_count=bm25_count,
            vector_count=vector_count,
            merged_count=merged_count,
            retrieval_duration_ms=duration_ms,
        )
        
        # Compute overlap and dominance from available data
        self._compute_overlap(result)
        self._compute_dominance(result)
        self._add_warnings(result)
        
        return result
    
    def analyze_with_candidates(
        self,
        run_id: str,
        bm25_candidates: list[dict],
        vector_candidates: list[dict],
        query_text: str = "",
    ) -> Optional[RetrievalDiagnosticResult]:
        """
        Analyze retrieval with full candidate data.
        
        Args:
            run_id: Run ID
            bm25_candidates: BM25 candidates with scores
            vector_candidates: Vector candidates with scores
            query_text: Query text
        
        Returns:
            RetrievalDiagnosticResult with full analysis
        """
        result = self.analyze_run(run_id, query_text)
        if result is None:
            return None
        
        # Parse candidates
        result.bm25_top_k = [
            RetrievalCandidate(
                doc_id=c.get("doc_id", ""),
                bm25_score=c.get("score"),
            )
            for c in bm25_candidates[:20]  # Top 20
        ]
        
        result.vector_top_k = [
            RetrievalCandidate(
                doc_id=c.get("doc_id", ""),
                vector_score=c.get("score"),
            )
            for c in vector_candidates[:20]  # Top 20
        ]
        
        # Compute detailed overlap
        bm25_ids = set(c.doc_id for c in result.bm25_top_k)
        vector_ids = set(c.doc_id for c in result.vector_top_k)
        
        result.overlap_count = len(bm25_ids & vector_ids)
        result.overlap_ratio = compute_overlap_ratio(bm25_ids, vector_ids)
        
        # Compute rank correlation
        bm25_ranked = [c.doc_id for c in result.bm25_top_k]
        vector_ranked = [c.doc_id for c in result.vector_top_k]
        result.rank_correlation = compute_rank_correlation(bm25_ranked, vector_ranked)
        
        # Compute score variance
        bm25_scores = [c.bm25_score for c in result.bm25_top_k if c.bm25_score is not None]
        vector_scores = [c.vector_score for c in result.vector_top_k if c.vector_score is not None]
        
        if len(bm25_scores) > 1:
            result.bm25_score_variance = statistics.variance(bm25_scores)
        if len(vector_scores) > 1:
            result.vector_score_variance = statistics.variance(vector_scores)
        
        return result
    
    def _compute_overlap(self, result: RetrievalDiagnosticResult) -> None:
        """Compute overlap from counts."""
        # Estimate overlap from merged count
        # If merged < bm25 + vector, there was deduplication
        expected_union = result.bm25_count + result.vector_count
        if expected_union > 0 and result.merged_count > 0:
            # Overlap = expected - actual
            estimated_overlap = max(0, expected_union - result.merged_count)
            result.overlap_count = estimated_overlap
            result.overlap_ratio = safe_divide(
                estimated_overlap,
                min(result.bm25_count, result.vector_count),
                0.0
            )
    
    def _compute_dominance(self, result: RetrievalDiagnosticResult) -> None:
        """Compute BM25 vs vector dominance."""
        total = result.bm25_count + result.vector_count
        if total > 0:
            result.bm25_dominance_pct = safe_divide(result.bm25_count, total, 0.0) * 100
            result.vector_dominance_pct = safe_divide(result.vector_count, total, 0.0) * 100
    
    def _add_warnings(self, result: RetrievalDiagnosticResult) -> None:
        """Add warnings based on analysis."""
        if result.bm25_count == 0 and result.vector_count == 0:
            result.warnings.append("No candidates retrieved - both BM25 and vector returned empty")
        
        if result.bm25_count == 0 and result.vector_count > 0:
            result.warnings.append("BM25 returned no results - vector-only retrieval")
        
        if result.vector_count == 0 and result.bm25_count > 0:
            result.warnings.append("Vector search returned no results - BM25-only retrieval")
        
        if result.overlap_ratio < 0.1 and result.bm25_count > 0 and result.vector_count > 0:
            result.warnings.append(
                f"Very low overlap ({result.overlap_ratio:.0%}) - BM25 and vector retrieving different docs"
            )
        
        if result.retrieval_duration_ms > 5000:
            result.warnings.append(
                f"Slow retrieval: {result.retrieval_duration_ms:.0f}ms"
            )
    
    def to_diagnostic_result(self, ret_result: RetrievalDiagnosticResult) -> DiagnosticResult:
        """Convert to standard DiagnosticResult for formatting."""
        summary = {
            "bm25_candidates": ret_result.bm25_count,
            "vector_candidates": ret_result.vector_count,
            "merged_candidates": ret_result.merged_count,
            "overlap_count": ret_result.overlap_count,
            "overlap_ratio": f"{ret_result.overlap_ratio:.1%}",
            "bm25_dominance": f"{ret_result.bm25_dominance_pct:.1f}%",
            "vector_dominance": f"{ret_result.vector_dominance_pct:.1f}%",
            "duration_ms": f"{ret_result.retrieval_duration_ms:.0f}",
        }
        
        # Details: top BM25 candidates
        details = []
        for c in ret_result.bm25_top_k[:5]:
            details.append({
                "source": "BM25",
                "doc_id": c.doc_id[:40] if len(c.doc_id) > 40 else c.doc_id,
                "score": f"{c.bm25_score:.4f}" if c.bm25_score else "-",
            })
        
        for c in ret_result.vector_top_k[:5]:
            details.append({
                "source": "Vector",
                "doc_id": c.doc_id[:40] if len(c.doc_id) > 40 else c.doc_id,
                "score": f"{c.vector_score:.4f}" if c.vector_score else "-",
            })
        
        return DiagnosticResult(
            phase="retrieval",
            query_id=ret_result.query_id,
            run_id=ret_result.run_id,
            summary=summary,
            details=details,
            warnings=ret_result.warnings,
        )
    
    def list_runs(self) -> list[str]:
        """List all available run IDs."""
        if not self.runs_path.exists():
            return []
        return [d.name for d in self.runs_path.iterdir() if d.is_dir()]
