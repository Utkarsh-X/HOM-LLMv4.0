"""
HOM-LLM Diagnostic Framework CLI

Single entry point for all diagnostics.

Usage:
    python diagnostics/run_diagnostics.py --run-id <run_id> --phases context,retrieval --format terminal
    python diagnostics/run_diagnostics.py --run-id <run_id> --query 1-10 --phases all --format json
    python diagnostics/run_diagnostics.py --embedding-analysis --format markdown

Supported query selectors:
    --query 3          Single query
    --query 1,5,7      List of queries
    --query 1-10       Range
    --query all        All queries

Supported phases:
    embedding, retrieval, reranking, context, all

Supported formats:
    terminal, json, markdown

Core Constraints (read-only, never mutates core):
    - No mutation of core HOM-LLM logic
    - No imports that change runtime behavior
    - No feedback into retrieval, ranking, or context
    - Strictly read-only
    - Deterministic and replayable
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from diagnostics.common.loaders import (
    TelemetryLoader,
    QueryLoader,
    ResponseLoader,
)
from diagnostics.common.formatters import (
    TerminalFormatter,
    JsonFormatter,
    MarkdownFormatter,
    DiagnosticResult,
)
from diagnostics.common.utils import parse_query_selector, ensure_reports_dir
from diagnostics.context.inspect_context import ContextDiagnostics
from diagnostics.retrieval.inspect_retrieval import RetrievalDiagnostics
from diagnostics.reranking.inspect_reranking import RerankingDiagnostics
from diagnostics.embedding.inspect_embeddings import EmbeddingDiagnostics


def get_formatter(format_type: str):
    """Get the appropriate formatter."""
    if format_type == "json":
        return JsonFormatter(pretty=True)
    elif format_type == "markdown":
        return MarkdownFormatter()
    else:
        return TerminalFormatter()


def run_context_diagnostics(
    run_id: str,
    artifacts_path: Path,
    indexes_path: Path,
) -> Optional[DiagnosticResult]:
    """Run context diagnostics for a run."""
    diagnostics = ContextDiagnostics(artifacts_path, indexes_path)
    result = diagnostics.analyze_run(run_id)
    
    if result is None:
        return None
    
    return diagnostics.to_diagnostic_result(result)


def run_retrieval_diagnostics(
    run_id: str,
    artifacts_path: Path,
    query_text: str = "",
) -> Optional[DiagnosticResult]:
    """Run retrieval diagnostics for a run."""
    diagnostics = RetrievalDiagnostics(artifacts_path)
    result = diagnostics.analyze_run(run_id, query_text)
    
    if result is None:
        return None
    
    return diagnostics.to_diagnostic_result(result)


def run_reranking_diagnostics(
    run_id: str,
    artifacts_path: Path,
) -> Optional[DiagnosticResult]:
    """Run reranking diagnostics for a run."""
    diagnostics = RerankingDiagnostics(artifacts_path)
    result = diagnostics.analyze_run(run_id)
    
    if result is None:
        return None
    
    return diagnostics.to_diagnostic_result(result)


def run_embedding_diagnostics(
    indexes_path: Path,
) -> DiagnosticResult:
    """Run embedding diagnostics."""
    diagnostics = EmbeddingDiagnostics(indexes_path)
    result = diagnostics.analyze()
    return diagnostics.to_diagnostic_result(result)


def find_run_for_query(
    query_id: int,
    eval_path: Path,
    artifacts_path: Path,
) -> Optional[str]:
    """Find the run ID for a specific query from eval responses."""
    response_loader = ResponseLoader(eval_path)
    latest_run = response_loader.get_latest_run()
    
    if not latest_run:
        return None
    
    responses = response_loader.load(latest_run)
    for response in responses:
        if response.query_id == query_id:
            return response.run_id
    
    return None


def list_available_runs(artifacts_path: Path) -> list[str]:
    """List all available run IDs."""
    runs_path = artifacts_path / "runs"
    if not runs_path.exists():
        return []
    return sorted([d.name for d in runs_path.iterdir() if d.is_dir()])


def main():
    parser = argparse.ArgumentParser(
        description="HOM-LLM Diagnostic Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Analyze a specific run:
    python run_diagnostics.py --run-id abc123 --phases context,retrieval

  Analyze queries 1-10:
    python run_diagnostics.py --query 1-10 --phases all --format markdown

  Run embedding waste analysis:
    python run_diagnostics.py --embedding-analysis

  List available runs:
    python run_diagnostics.py --list-runs
        """
    )
    
    parser.add_argument(
        "--run-id",
        type=str,
        help="Run ID to analyze",
    )
    
    parser.add_argument(
        "--query",
        type=str,
        default="all",
        help="Query selector: single (3), list (1,5,7), range (1-10), or 'all'",
    )
    
    parser.add_argument(
        "--phases",
        type=str,
        default="context,retrieval,reranking",
        help="Comma-separated phases: embedding,retrieval,reranking,context,all",
    )
    
    parser.add_argument(
        "--format",
        type=str,
        choices=["terminal", "json", "markdown"],
        default="terminal",
        help="Output format",
    )
    
    parser.add_argument(
        "--embedding-analysis",
        action="store_true",
        help="Run embedding waste analysis only",
    )
    
    parser.add_argument(
        "--list-runs",
        action="store_true",
        help="List available run IDs",
    )
    
    parser.add_argument(
        "--save-report",
        action="store_true",
        help="Save report to diagnostics/reports/",
    )
    
    parser.add_argument(
        "--artifacts-path",
        type=str,
        default=str(PROJECT_ROOT / "artifacts"),
        help="Path to artifacts directory",
    )
    
    parser.add_argument(
        "--indexes-path",
        type=str,
        default=str(PROJECT_ROOT / "indexes"),
        help="Path to indexes directory",
    )
    
    parser.add_argument(
        "--eval-path",
        type=str,
        default=str(PROJECT_ROOT / "eval"),
        help="Path to eval directory",
    )
    
    args = parser.parse_args()
    
    artifacts_path = Path(args.artifacts_path)
    indexes_path = Path(args.indexes_path)
    eval_path = Path(args.eval_path)
    diagnostics_path = Path(__file__).parent
    
    formatter = get_formatter(args.format)
    
    # Handle --list-runs
    if args.list_runs:
        runs = list_available_runs(artifacts_path)
        print(f"Available runs ({len(runs)}):")
        for run_id in runs[-20:]:  # Show last 20
            print(f"  {run_id}")
        return
    
    # Handle --embedding-analysis
    if args.embedding_analysis:
        print("Running embedding analysis...\n")
        result = run_embedding_diagnostics(indexes_path)
        output = formatter.format(result)
        print(output)
        
        if args.save_report:
            reports_dir = ensure_reports_dir(diagnostics_path, "summary")
            ext = ".json" if args.format == "json" else ".md" if args.format == "markdown" else ".txt"
            filepath = reports_dir / f"embedding_analysis{ext}"
            formatter.save(output, filepath)
            print(f"\nReport saved to: {filepath}")
        
        return
    
    # Parse phases
    if args.phases == "all":
        phases = ["embedding", "retrieval", "reranking", "context"]
    else:
        phases = [p.strip() for p in args.phases.split(",")]
    
    # Determine runs to analyze
    run_ids = []
    
    if args.run_id:
        run_ids = [args.run_id]
    else:
        # Parse query selector
        query_ids = parse_query_selector(args.query)
        
        if not query_ids:
            # "all" - use latest eval run
            response_loader = ResponseLoader(eval_path)
            latest_run = response_loader.get_latest_run()
            
            if latest_run:
                responses = response_loader.load(latest_run)
                for response in responses:
                    if response.run_id:
                        run_ids.append(response.run_id)
        else:
            # Specific queries
            for qid in query_ids:
                run_id = find_run_for_query(qid, eval_path, artifacts_path)
                if run_id:
                    run_ids.append(run_id)
    
    if not run_ids:
        print("No runs found to analyze.")
        print("Use --list-runs to see available runs, or --run-id to specify one.")
        return
    
    # Run diagnostics
    all_results = []
    
    for run_id in run_ids:
        print(f"\nAnalyzing run: {run_id}")
        print("-" * 50)
        
        run_results = []
        
        if "context" in phases:
            result = run_context_diagnostics(run_id, artifacts_path, indexes_path)
            if result:
                run_results.append(result)
                print(formatter.format(result))
                print()
        
        if "retrieval" in phases:
            result = run_retrieval_diagnostics(run_id, artifacts_path)
            if result:
                run_results.append(result)
                print(formatter.format(result))
                print()
        
        if "reranking" in phases:
            result = run_reranking_diagnostics(run_id, artifacts_path)
            if result:
                run_results.append(result)
                print(formatter.format(result))
                print()
        
        if "embedding" in phases:
            result = run_embedding_diagnostics(indexes_path)
            run_results.append(result)
            print(formatter.format(result))
            print()
        
        all_results.extend(run_results)
        
        # Save per-query report if requested
        if args.save_report and run_results:
            reports_dir = ensure_reports_dir(diagnostics_path, "per_query")
            ext = ".json" if args.format == "json" else ".md" if args.format == "markdown" else ".txt"
            filepath = reports_dir / f"{run_id}{ext}"
            
            combined_output = "\n\n".join(formatter.format(r) for r in run_results)
            formatter.save(combined_output, filepath)
    
    # Print summary if multiple runs
    if len(run_ids) > 1 and all_results:
        print("\n" + "=" * 50)
        summary = formatter.format_summary(all_results)
        print(summary)
        
        if args.save_report:
            reports_dir = ensure_reports_dir(diagnostics_path, "summary")
            ext = ".json" if args.format == "json" else ".md" if args.format == "markdown" else ".txt"
            filepath = reports_dir / f"summary{ext}"
            formatter.save(summary, filepath)
            print(f"\nSummary saved to: {filepath}")


if __name__ == "__main__":
    main()
