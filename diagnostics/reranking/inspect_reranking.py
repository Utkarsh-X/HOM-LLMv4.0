"""
Re-ranking Diagnostics (Quality, Not Speed)

Exposes:
- Original rank
- Rerank score
- Rank delta
- Document length

Derived signals:
- Rank churn %
- Top-N stability
- Long-document bias detection
- Reranker effectiveness score (relative)

Note: Performance diagnostics already exist; this focuses on DECISION QUALITY.

Read-only: Never modifies core system artifacts.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import json
import statistics

from diagnostics.common.formatters import DiagnosticResult
from diagnostics.common.utils import safe_divide


@dataclass(frozen=True)
class RankedCandidate:
    """A candidate with ranking information."""
    
    doc_id: str
    original_rank: int
    final_rank: int
    rerank_score: Optional[float] = None
    base_score: Optional[float] = None
    struct_bonus: Optional[float] = None
    final_score: Optional[float] = None
    content_length: int = 0
    
    @property
    def rank_delta(self) -> int:
        """Change in rank (positive = moved up, negative = moved down)."""
        return self.original_rank - self.final_rank


@dataclass
class RerankingDiagnosticResult:
    """Complete reranking diagnostic result."""
    
    query_id: str | int | None
    run_id: str | None
    
    # Counts
    candidate_count: int = 0
    reranked_count: int = 0
    
    # Reranker status
    reranker_used: bool = False
    reranker_unavailable: bool = False
    
    # Duration
    ranking_duration_ms: float = 0.0
    
    # Quality metrics
    rank_churn_pct: float = 0.0  # % of candidates that changed position
    top_n_stability: float = 0.0  # % of top-N that stayed in top-N
    avg_rank_delta: float = 0.0
    max_rank_delta: int = 0
    
    # Bias detection
    long_doc_bias_score: float = 0.0  # Correlation between length and rank improvement
    
    # Effectiveness
    reranker_effectiveness: float = 0.0  # Relative improvement score
    
    # Candidates
    candidates: list[RankedCandidate] = field(default_factory=list)
    
    # Top movers
    top_promotions: list[RankedCandidate] = field(default_factory=list)
    top_demotions: list[RankedCandidate] = field(default_factory=list)
    
    # Warnings
    warnings: list[str] = field(default_factory=list)


class RerankingDiagnostics:
    """
    Reranking diagnostics.
    
    Analyzes reranker's impact on ranking quality:
    - How much did rankings change?
    - Which documents moved the most?
    - Is there bias toward longer documents?
    - How effective is the reranker?
    
    Read-only: Never modifies source data.
    """
    
    def __init__(self, artifacts_path: Path):
        """
        Initialize reranking diagnostics.
        
        Args:
            artifacts_path: Path to artifacts directory
        """
        self.artifacts_path = Path(artifacts_path)
        self.runs_path = self.artifacts_path / "runs"
    
    def analyze_run(self, run_id: str) -> Optional[RerankingDiagnosticResult]:
        """
        Analyze reranking phase for a specific run.
        
        Args:
            run_id: Run ID to analyze
        
        Returns:
            RerankingDiagnosticResult or None if run not found
        """
        telemetry_file = self.runs_path / run_id / "telemetry.json"
        if not telemetry_file.exists():
            return None
        
        try:
            with open(telemetry_file, "r", encoding="utf-8") as f:
                telemetry = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
        
        # Extract ranking phase data
        ranking_phase = telemetry.get("phases", {}).get("RANKING", {})
        
        candidate_count = ranking_phase.get("candidates", 0)
        reranker_used = ranking_phase.get("reranker", False)
        reranker_unavailable = ranking_phase.get("reranker_unavailable", False)
        duration_ms = ranking_phase.get("duration_ms", 0.0)
        
        # Build result
        result = RerankingDiagnosticResult(
            query_id=None,
            run_id=run_id,
            candidate_count=candidate_count,
            reranker_used=reranker_used,
            reranker_unavailable=reranker_unavailable,
            ranking_duration_ms=duration_ms,
        )
        
        # Add warnings
        self._add_warnings(result)
        
        return result
    
    def analyze_with_traces(
        self,
        run_id: str,
        debug_traces: list[dict],
        original_order: list[str],
    ) -> Optional[RerankingDiagnosticResult]:
        """
        Analyze reranking with full debug trace data.
        
        Args:
            run_id: Run ID
            debug_traces: Debug traces from ranking pipeline
            original_order: Original candidate order (doc IDs before ranking)
        
        Returns:
            RerankingDiagnosticResult with full analysis
        """
        result = self.analyze_run(run_id)
        if result is None:
            return None
        
        # Build candidate list with rank information
        original_ranks = {doc_id: i for i, doc_id in enumerate(original_order)}
        
        candidates = []
        for final_rank, trace in enumerate(debug_traces):
            doc_id = trace.get("candidate_id", "")
            original_rank = original_ranks.get(doc_id, final_rank)
            
            candidate = RankedCandidate(
                doc_id=doc_id,
                original_rank=original_rank,
                final_rank=final_rank,
                rerank_score=trace.get("rerank_score"),
                base_score=trace.get("base_score"),
                struct_bonus=trace.get("struct_bonus"),
                final_score=trace.get("final_score"),
                content_length=trace.get("content_length", 0),
            )
            candidates.append(candidate)
        
        result.candidates = candidates
        result.reranked_count = len(candidates)
        
        # Compute quality metrics
        if candidates:
            self._compute_rank_churn(result)
            self._compute_top_n_stability(result)
            self._find_top_movers(result)
            self._detect_length_bias(result)
            self._compute_effectiveness(result)
        
        return result
    
    def _compute_rank_churn(self, result: RerankingDiagnosticResult) -> None:
        """Compute rank churn percentage."""
        if not result.candidates:
            return
        
        changed = sum(1 for c in result.candidates if c.rank_delta != 0)
        result.rank_churn_pct = safe_divide(changed, len(result.candidates), 0.0) * 100
        
        deltas = [abs(c.rank_delta) for c in result.candidates]
        if deltas:
            result.avg_rank_delta = statistics.mean(deltas)
            result.max_rank_delta = max(deltas)
    
    def _compute_top_n_stability(self, result: RerankingDiagnosticResult, n: int = 10) -> None:
        """Compute how stable the top-N is."""
        if not result.candidates:
            return
        
        # Find which candidates were originally in top N
        original_top_n = set(
            c.doc_id for c in result.candidates if c.original_rank < n
        )
        
        # Find which are now in top N
        final_top_n = set(
            c.doc_id for c in result.candidates if c.final_rank < n
        )
        
        if original_top_n:
            stable = len(original_top_n & final_top_n)
            result.top_n_stability = safe_divide(stable, len(original_top_n), 0.0) * 100
    
    def _find_top_movers(self, result: RerankingDiagnosticResult) -> None:
        """Find candidates with largest rank changes."""
        if not result.candidates:
            return
        
        sorted_by_delta = sorted(result.candidates, key=lambda c: c.rank_delta, reverse=True)
        
        # Top promotions (moved up the most)
        result.top_promotions = [c for c in sorted_by_delta[:3] if c.rank_delta > 0]
        
        # Top demotions (moved down the most)
        result.top_demotions = [c for c in sorted_by_delta[-3:] if c.rank_delta < 0]
    
    def _detect_length_bias(self, result: RerankingDiagnosticResult) -> None:
        """Detect bias toward longer documents."""
        candidates_with_length = [
            c for c in result.candidates if c.content_length > 0
        ]
        
        if len(candidates_with_length) < 3:
            return
        
        # Simple correlation: do longer docs tend to move up?
        lengths = [c.content_length for c in candidates_with_length]
        deltas = [c.rank_delta for c in candidates_with_length]
        
        # Normalize
        mean_length = statistics.mean(lengths)
        mean_delta = statistics.mean(deltas)
        
        if mean_length == 0:
            return
        
        # Compute correlation (simplified)
        numerator = sum(
            (l - mean_length) * (d - mean_delta)
            for l, d in zip(lengths, deltas)
        )
        
        var_length = sum((l - mean_length) ** 2 for l in lengths)
        var_delta = sum((d - mean_delta) ** 2 for d in deltas)
        
        denominator = (var_length * var_delta) ** 0.5
        
        if denominator > 0:
            result.long_doc_bias_score = numerator / denominator
            
            if result.long_doc_bias_score > 0.5:
                result.warnings.append(
                    f"Possible length bias: correlation {result.long_doc_bias_score:.2f}"
                )
    
    def _compute_effectiveness(self, result: RerankingDiagnosticResult) -> None:
        """Compute reranker effectiveness score."""
        if not result.candidates or not result.reranker_used:
            return
        
        # Effectiveness = average rank improvement for reranked candidates
        reranked = [c for c in result.candidates if c.rerank_score is not None]
        
        if reranked:
            improvements = [c.rank_delta for c in reranked if c.rank_delta > 0]
            if improvements:
                result.reranker_effectiveness = statistics.mean(improvements)
    
    def _add_warnings(self, result: RerankingDiagnosticResult) -> None:
        """Add warnings based on analysis."""
        if result.reranker_unavailable:
            result.warnings.append("Reranker unavailable - ranking degraded")
        
        if not result.reranker_used and not result.reranker_unavailable:
            result.warnings.append("Reranker disabled - using base scores only")
        
        if result.ranking_duration_ms > 30000:
            result.warnings.append(
                f"Very slow ranking: {result.ranking_duration_ms:.0f}ms"
            )
        
        if result.rank_churn_pct > 80:
            result.warnings.append(
                f"High rank churn: {result.rank_churn_pct:.0f}% of candidates changed position"
            )
        
        if result.top_n_stability < 50 and result.candidate_count > 10:
            result.warnings.append(
                f"Low top-N stability: only {result.top_n_stability:.0f}% remained in top 10"
            )
    
    def to_diagnostic_result(self, rnk_result: RerankingDiagnosticResult) -> DiagnosticResult:
        """Convert to standard DiagnosticResult for formatting."""
        summary = {
            "candidate_count": rnk_result.candidate_count,
            "reranker_used": "Yes" if rnk_result.reranker_used else "No",
            "reranker_unavailable": "Yes" if rnk_result.reranker_unavailable else "No",
            "rank_churn": f"{rnk_result.rank_churn_pct:.1f}%",
            "top_10_stability": f"{rnk_result.top_n_stability:.1f}%",
            "avg_rank_delta": f"{rnk_result.avg_rank_delta:.1f}",
            "max_rank_delta": rnk_result.max_rank_delta,
            "length_bias_score": f"{rnk_result.long_doc_bias_score:.2f}",
            "duration_ms": f"{rnk_result.ranking_duration_ms:.0f}",
        }
        
        # Details: top promotions and demotions
        details = []
        
        for c in rnk_result.top_promotions:
            details.append({
                "type": "promotion",
                "doc_id": c.doc_id[:30] if len(c.doc_id) > 30 else c.doc_id,
                "rank_change": f"+{c.rank_delta}",
                "final_rank": c.final_rank + 1,  # 1-indexed for display
            })
        
        for c in rnk_result.top_demotions:
            details.append({
                "type": "demotion",
                "doc_id": c.doc_id[:30] if len(c.doc_id) > 30 else c.doc_id,
                "rank_change": str(c.rank_delta),
                "final_rank": c.final_rank + 1,
            })
        
        return DiagnosticResult(
            phase="reranking",
            query_id=rnk_result.query_id,
            run_id=rnk_result.run_id,
            summary=summary,
            details=details,
            warnings=rnk_result.warnings,
        )
    
    def list_runs(self) -> list[str]:
        """List all available run IDs."""
        if not self.runs_path.exists():
            return []
        return [d.name for d in self.runs_path.iterdir() if d.is_dir()]
