"""Verification script for the diagnostic framework."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def main():
    print("=" * 60)
    print("HOM-LLM DIAGNOSTIC FRAMEWORK - VERIFICATION REPORT")
    print("=" * 60)
    print()

    # 1. Module imports
    print("1. MODULE IMPORTS")
    all_passed = True
    
    modules = [
        ("common.loaders", "diagnostics.common.loaders"),
        ("common.formatters", "diagnostics.common.formatters"),
        ("common.utils", "diagnostics.common.utils"),
        ("context", "diagnostics.context"),
        ("retrieval", "diagnostics.retrieval"),
        ("reranking", "diagnostics.reranking"),
        ("embedding", "diagnostics.embedding"),
    ]
    
    for name, module_path in modules:
        try:
            __import__(module_path)
            print(f"   {name}: PASS")
        except Exception as e:
            print(f"   {name}: FAIL - {e}")
            all_passed = False

    # 2. Data loading
    print()
    print("2. DATA LOADING")
    
    from diagnostics.common.loaders import TelemetryLoader, IndexLoader, QueryLoader
    
    artifacts = PROJECT_ROOT / "artifacts"
    indexes = PROJECT_ROOT / "indexes"
    eval_path = PROJECT_ROOT / "eval"
    
    tl = TelemetryLoader(artifacts)
    runs = tl.list_runs()
    print(f"   Telemetry runs: {len(runs)}")
    
    il = IndexLoader(indexes)
    meta = il.load()
    print(f"   Index symbols: {len(meta.symbols)}, files: {len(meta.files)}")
    
    ql = QueryLoader(eval_path)
    queries = ql.load()
    print(f"   Eval queries: {len(queries)}")

    # 3. Diagnostic analysis
    print()
    print("3. DIAGNOSTIC ANALYSIS")
    
    from diagnostics.embedding import EmbeddingDiagnostics
    from diagnostics.context import ContextDiagnostics
    from diagnostics.retrieval import RetrievalDiagnostics
    from diagnostics.reranking import RerankingDiagnostics
    
    emb = EmbeddingDiagnostics(indexes)
    result = emb.analyze()
    print(f"   Embedding: {result.total_embeddings} embeddings, {result.oversized_count} oversized")
    
    if runs:
        ctx = ContextDiagnostics(artifacts, indexes)
        result = ctx.analyze_run(runs[0])
        if result:
            print(f"   Context: {result.total_blocks} blocks, {result.total_tokens} tokens")
        
        ret = RetrievalDiagnostics(artifacts)
        result = ret.analyze_run(runs[0])
        if result:
            print(f"   Retrieval: BM25={result.bm25_count}, Vector={result.vector_count}")
        
        rnk = RerankingDiagnostics(artifacts)
        result = rnk.analyze_run(runs[0])
        if result:
            print(f"   Reranking: {result.candidate_count} candidates, reranker={result.reranker_used}")

    # 4. Output formats
    print()
    print("4. OUTPUT FORMATS")
    
    from diagnostics.common.formatters import (
        DiagnosticResult, 
        TerminalFormatter, 
        JsonFormatter, 
        MarkdownFormatter
    )
    
    test_result = DiagnosticResult(
        phase="test",
        query_id=None,
        run_id=None,
        summary={"metric": 1},
        details=[],
        warnings=[]
    )
    
    tf = TerminalFormatter()
    jf = JsonFormatter()
    mf = MarkdownFormatter()
    
    print(f"   Terminal: {'PASS' if tf.format(test_result) else 'FAIL'}")
    print(f"   JSON: {'PASS' if jf.format(test_result) else 'FAIL'}")
    print(f"   Markdown: {'PASS' if mf.format(test_result) else 'FAIL'}")
    
    # 5. Query selector
    print()
    print("5. QUERY SELECTOR")
    
    from diagnostics.common.utils import parse_query_selector
    
    tests = [
        ("3", [3]),
        ("1,5,7", [1, 5, 7]),
        ("1-5", [1, 2, 3, 4, 5]),
        ("all", []),
    ]
    
    for selector, expected in tests:
        result = parse_query_selector(selector)
        status = "PASS" if result == expected else f"FAIL (got {result})"
        print(f"   '{selector}' -> {expected}: {status}")
        if result != expected:
            all_passed = False

    print()
    print("=" * 60)
    if all_passed:
        print("ALL VERIFICATION TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)


if __name__ == "__main__":
    main()
