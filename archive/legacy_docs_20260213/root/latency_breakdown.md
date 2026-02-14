# Retrieval Latency Breakdown - run_20260201_101716 vs run_20260204_173223

## Summary
- Old avg retrieval: 1978.3 ms (1.98 s)
- New avg retrieval: 16335.8 ms (16.34 s)
- Avg retrieval delta: 14357.6 ms (14.36 s)
- Old avg ranking: 24577.7 ms (24.58 s)
- New avg ranking: 21604.5 ms (21.60 s)

## Phase Timing Table (averages across queries 1,3,5,8,16,18)

| Phase | Old avg | New avg | Delta |
| --- | --- | --- | --- |
| retrieval_total_ms | 1978.3 ms (1.98 s) | 16335.8 ms (16.34 s) | 14357.6 ms (14.36 s) |
| ranking_total_ms | 24577.7 ms (24.58 s) | 21604.5 ms (21.60 s) | -2973.3 ms (-2.97 s) |
| bm25_ms | N/A | 16.1 ms (0.02 s) | N/A |
| vector_ms | N/A | 301.3 ms (0.30 s) | N/A |
| merge_ms | N/A | 13807.9 ms (13.81 s) | N/A |
| graph_stitch_ms | N/A | 24.5 ms (0.02 s) | N/A |
| expansion_ms | N/A | 2118.1 ms (2.12 s) | N/A |
| granularity_ms | N/A | 14.2 ms (0.01 s) | N/A |
| precision_ms | N/A | 0.1 ms (0.00 s) | N/A |
| mmr_emb_ms | N/A | N/A | N/A |
| mmr_ms | N/A | N/A | N/A |
| prep_ms | N/A | 0.1 ms (0.00 s) | N/A |

## Root Causes (data-backed)
- Hybrid merge time dominates retrieval: 13807.9 ms (~84.5% of new retrieval).
- Structural expansion adds material time: 2118.1 ms (~13.0% of new retrieval).
- Vector search time is comparatively small: 301.3 ms (~1.8% of new retrieval).

## Fix Targets (based on measured time)
- If you need immediate latency reduction, target `merge_ms` and `expansion_ms` first (largest observed contributors).
- Reranker time is not the driver in this comparison (ranking average is lower in the new run).
- MMR subphase timings are N/A in telemetry (no mmr_* values recorded in this run).
