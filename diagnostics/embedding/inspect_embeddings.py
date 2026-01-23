"""
Embedding Diagnostics (Waste Analysis)

Exposes:
- embedding_id
- source (file / symbol / chunk)
- text length (chars)
- token count
- embedding dimension
- embedding latency (if available)

Derived diagnostics:
- Chunk size distribution
- Oversized / undersized chunks
- % embeddings never retrieved
- Top-K most frequently retrieved embeddings

Read-only: Never modifies core system artifacts.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import json
import statistics

from diagnostics.common.formatters import DiagnosticResult
from diagnostics.common.utils import safe_divide, compute_percentile


@dataclass(frozen=True)
class EmbeddingInfo:
    """Information about a single embedding."""
    
    embedding_id: str
    source_type: str  # "file", "symbol", "chunk"
    source_file: str
    text_length: int  # characters
    token_count: int
    line_range: tuple[int, int]
    symbol_name: Optional[str] = None


@dataclass
class EmbeddingDiagnosticResult:
    """Complete embedding diagnostic result."""
    
    # Counts
    total_embeddings: int = 0
    file_embeddings: int = 0
    symbol_embeddings: int = 0
    
    # Size distribution
    avg_text_length: float = 0.0
    median_text_length: float = 0.0
    min_text_length: int = 0
    max_text_length: int = 0
    
    avg_token_count: float = 0.0
    median_token_count: float = 0.0
    
    # Size buckets
    undersized_count: int = 0  # < 50 tokens
    optimal_count: int = 0     # 50-500 tokens
    oversized_count: int = 0   # > 500 tokens
    
    # Retrieval stats (if available)
    never_retrieved_pct: float = 0.0
    top_k_retrieved: list[tuple[str, int]] = field(default_factory=list)
    
    # Embeddings list
    embeddings: list[EmbeddingInfo] = field(default_factory=list)
    
    # Warnings
    warnings: list[str] = field(default_factory=list)


class EmbeddingDiagnostics:
    """
    Embedding diagnostics.
    
    Analyzes embedding index to understand:
    - Chunk size distribution
    - Waste (never-retrieved embeddings)
    - Frequently retrieved embeddings
    
    Read-only: Never modifies source data.
    """
    
    UNDERSIZED_THRESHOLD = 50   # tokens
    OVERSIZED_THRESHOLD = 500   # tokens
    
    def __init__(self, indexes_path: Path):
        """
        Initialize embedding diagnostics.
        
        Args:
            indexes_path: Path to indexes directory
        """
        self.indexes_path = Path(indexes_path)
    
    def analyze(self) -> EmbeddingDiagnosticResult:
        """
        Analyze embedding index.
        
        Returns:
            EmbeddingDiagnosticResult with analysis
        """
        result = EmbeddingDiagnosticResult()
        
        # Load symbols (each symbol = one embedding)
        symbols = self._load_symbols()
        files = self._load_files()
        
        if not symbols:
            result.warnings.append("No symbols found in index")
            return result
        
        # Build embedding info list
        embeddings = []
        text_lengths = []
        token_counts = []
        
        for symbol in symbols:
            # Estimate token count from line count (rough: ~10 tokens per line)
            start_line = symbol.get("start_line", 0)
            end_line = symbol.get("end_line", 0)
            line_count = max(0, end_line - start_line + 1)
            estimated_tokens = line_count * 10
            
            # Estimate text length from line count (~80 chars per line)
            estimated_chars = line_count * 80
            
            embedding = EmbeddingInfo(
                embedding_id=symbol.get("id", ""),
                source_type="symbol",
                source_file=symbol.get("file", ""),
                text_length=estimated_chars,
                token_count=estimated_tokens,
                line_range=(start_line, end_line),
                symbol_name=symbol.get("name"),
            )
            embeddings.append(embedding)
            
            text_lengths.append(estimated_chars)
            token_counts.append(estimated_tokens)
        
        result.embeddings = embeddings
        result.total_embeddings = len(embeddings)
        result.symbol_embeddings = len(embeddings)
        result.file_embeddings = len(files)
        
        # Compute size statistics
        if text_lengths:
            result.avg_text_length = statistics.mean(text_lengths)
            result.median_text_length = statistics.median(text_lengths)
            result.min_text_length = min(text_lengths)
            result.max_text_length = max(text_lengths)
        
        if token_counts:
            result.avg_token_count = statistics.mean(token_counts)
            result.median_token_count = statistics.median(token_counts)
            
            # Size buckets
            result.undersized_count = sum(1 for t in token_counts if t < self.UNDERSIZED_THRESHOLD)
            result.optimal_count = sum(
                1 for t in token_counts 
                if self.UNDERSIZED_THRESHOLD <= t <= self.OVERSIZED_THRESHOLD
            )
            result.oversized_count = sum(1 for t in token_counts if t > self.OVERSIZED_THRESHOLD)
        
        # Add warnings
        self._add_warnings(result)
        
        return result
    
    def analyze_retrieval_frequency(
        self,
        telemetry_runs: list[dict],
    ) -> EmbeddingDiagnosticResult:
        """
        Analyze retrieval frequency across multiple runs.
        
        Args:
            telemetry_runs: List of telemetry data dicts
        
        Returns:
            EmbeddingDiagnosticResult with retrieval stats
        """
        result = self.analyze()
        
        # Count retrieval frequency per embedding
        retrieval_counts: dict[str, int] = {}
        
        for run_data in telemetry_runs:
            # Extract retrieved candidate IDs (if available in telemetry)
            candidates = run_data.get("retrieved_candidates", [])
            for doc_id in candidates:
                retrieval_counts[doc_id] = retrieval_counts.get(doc_id, 0) + 1
        
        if not retrieval_counts and result.total_embeddings > 0:
            # No retrieval data available
            return result
        
        # Compute never-retrieved percentage
        all_ids = set(e.embedding_id for e in result.embeddings)
        retrieved_ids = set(retrieval_counts.keys())
        never_retrieved = all_ids - retrieved_ids
        
        result.never_retrieved_pct = safe_divide(
            len(never_retrieved), len(all_ids), 0.0
        ) * 100
        
        # Top K most frequently retrieved
        sorted_counts = sorted(
            retrieval_counts.items(), key=lambda x: x[1], reverse=True
        )
        result.top_k_retrieved = sorted_counts[:10]
        
        if result.never_retrieved_pct > 50:
            result.warnings.append(
                f"High embedding waste: {result.never_retrieved_pct:.0f}% never retrieved"
            )
        
        return result
    
    def _load_symbols(self) -> list[dict]:
        """Load symbols from index."""
        symbols_file = self.indexes_path / "symbols.json"
        if not symbols_file.exists():
            return []
        
        try:
            with open(symbols_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("symbols", [])
        except (json.JSONDecodeError, IOError):
            return []
    
    def _load_files(self) -> list[dict]:
        """Load files from index."""
        files_file = self.indexes_path / "files.json"
        if not files_file.exists():
            return []
        
        try:
            with open(files_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("files", [])
        except (json.JSONDecodeError, IOError):
            return []
    
    def _add_warnings(self, result: EmbeddingDiagnosticResult) -> None:
        """Add warnings based on analysis."""
        if result.total_embeddings == 0:
            result.warnings.append("No embeddings found in index")
            return
        
        undersized_pct = safe_divide(result.undersized_count, result.total_embeddings, 0.0) * 100
        oversized_pct = safe_divide(result.oversized_count, result.total_embeddings, 0.0) * 100
        
        if undersized_pct > 30:
            result.warnings.append(
                f"Many undersized chunks: {undersized_pct:.0f}% have < {self.UNDERSIZED_THRESHOLD} tokens"
            )
        
        if oversized_pct > 20:
            result.warnings.append(
                f"Many oversized chunks: {oversized_pct:.0f}% have > {self.OVERSIZED_THRESHOLD} tokens"
            )
        
        if result.max_text_length > 10000:
            result.warnings.append(
                f"Very large chunks detected: max {result.max_text_length} chars"
            )
    
    def to_diagnostic_result(self, emb_result: EmbeddingDiagnosticResult) -> DiagnosticResult:
        """Convert to standard DiagnosticResult for formatting."""
        summary = {
            "total_embeddings": emb_result.total_embeddings,
            "symbol_embeddings": emb_result.symbol_embeddings,
            "file_embeddings": emb_result.file_embeddings,
            "avg_text_length": f"{emb_result.avg_text_length:.0f} chars",
            "avg_token_count": f"{emb_result.avg_token_count:.0f}",
            "undersized_chunks": emb_result.undersized_count,
            "optimal_chunks": emb_result.optimal_count,
            "oversized_chunks": emb_result.oversized_count,
            "never_retrieved_pct": f"{emb_result.never_retrieved_pct:.1f}%",
        }
        
        # Details: size distribution examples
        details = []
        
        # Show a few oversized chunks
        oversized = [e for e in emb_result.embeddings if e.token_count > self.OVERSIZED_THRESHOLD][:3]
        for e in oversized:
            details.append({
                "type": "oversized",
                "symbol": e.symbol_name or "-",
                "tokens": f"~{e.token_count}",
                "file": e.source_file.split("\\")[-1] if "\\" in e.source_file else e.source_file.split("/")[-1],
            })
        
        # Show a few undersized chunks
        undersized = [e for e in emb_result.embeddings if e.token_count < self.UNDERSIZED_THRESHOLD][:3]
        for e in undersized:
            details.append({
                "type": "undersized",
                "symbol": e.symbol_name or "-",
                "tokens": f"~{e.token_count}",
                "file": e.source_file.split("\\")[-1] if "\\" in e.source_file else e.source_file.split("/")[-1],
            })
        
        return DiagnosticResult(
            phase="embedding",
            query_id=None,
            run_id=None,
            summary=summary,
            details=details,
            warnings=emb_result.warnings,
        )
