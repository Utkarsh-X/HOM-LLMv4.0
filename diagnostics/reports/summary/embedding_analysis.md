# EMBEDDING Diagnostic Report


## Summary

| Metric | Value |
|--------|-------|
| Total Embeddings | 316 |
| Symbol Embeddings | 316 |
| File Embeddings | 41 |
| Avg Text Length | 2021 chars |
| Avg Token Count | 253 |
| Undersized Chunks | 53 |
| Optimal Chunks | 235 |
| Oversized Chunks | 28 |
| Never Retrieved Pct | 0.0% |

## Warnings

- Very large chunks detected: max 44000 chars

## Details

| # | type | symbol | tokens | file |
| --- | --- | --- | --- | --- |
| 1 | oversized | BatchProcessor | ~960 | batch_processor.py |
| 2 | oversized | process | ~650 | batch_processor.py |
| 3 | oversized | JobQueue | ~1630 | job_queue.py |
| 4 | undersized | get_stats | ~30 | batch_processor.py |
| 5 | undersized | get_queue_size | ~40 | job_queue.py |
| 6 | undersized | stop | ~30 | worker.py |