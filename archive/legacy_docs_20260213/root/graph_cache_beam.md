# Graph Cache + Beam Pruning Report

## Runs Compared
- Before: run_20260204_173223
- After: run_20260206_085300 (latency/blocks)
- Judge: run_20260206_090527 (quality)

## Latency (avg across queries 1,3,5,8,16,18)

| Metric | Before | After | Delta |
| --- | --- | --- | --- |
| Retrieval total | 16335.8 ms | 20944.4 ms | 4608.5 ms |
| Expansion phase | 2118.1 ms | 2567.7 ms | 449.6 ms |

## Quality Impact
- Win rate: 83.3% (5 improved / 1 regressed)
- Q16 BatchProcessor recall (context block_id contains 'BatchProcessor'): False

## Blocks Retrieved (pollution proxy)
- Context block counts used as proxy (provenance not persisted in artifacts).
- Avg context blocks: before 14.3 vs after 15.0
- BatchProcessor blocks across all queries: before 0 vs after 1