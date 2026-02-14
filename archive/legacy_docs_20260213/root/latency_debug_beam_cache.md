# Graph Cache + Beam Debug Report

## Log Excerpts
```
2026-02-06 17:09:20 INFO GraphTopology: Loaded cache nodes=165 edges=621 in 5.6 ms
2026-02-06 17:10:55 INFO GraphTopology: Loaded cache nodes=165 edges=621 in 5.8 ms
2026-02-06 17:12:17 INFO GraphTopology: Loaded cache nodes=165 edges=621 in 6.0 ms
```
```
2026-02-06 17:09:35 INFO GraphStitch: query="Trace the execution flow when an admin user calls the admin_search_endpoint thro" cache_used=True cache_hits=40 cache_fallbacks=0 bfs_ms=0.3 entity_info_ms=10.1 content_ms=0.0 visited=45 neighbors_before=54 neighbors_after=54 avg_high=16.5 avg_low=10.5 avg_total=27.0 avg_after=27.0 additions=0
2026-02-06 17:11:09 INFO GraphStitch: query="How does the query optimizer resolve conflicts between PREDICATE_PUSHDOWN and CO" cache_used=True cache_hits=35 cache_fallbacks=0 bfs_ms=0.2 entity_info_ms=9.5 content_ms=0.0 visited=39 neighbors_before=77 neighbors_after=66 avg_high=18.5 avg_low=14.5 avg_total=38.5 avg_after=33.0 additions=0
2026-02-06 17:12:32 INFO GraphStitch: query="What happens when L1 memory, L2 Redis, and L3 database caches all miss, and how " cache_used=True cache_hits=32 cache_fallbacks=0 bfs_ms=0.2 entity_info_ms=5.2 content_ms=0.0 visited=36 neighbors_before=37 neighbors_after=36 avg_high=11.5 avg_low=6.5 avg_total=18.5 avg_after=18.0 additions=0
2026-02-06 17:13:43 INFO GraphStitch: query="How does ConnectionPool behave when all connections are in use and callers wait " cache_used=True cache_hits=35 cache_fallbacks=0 bfs_ms=0.2 entity_info_ms=6.4 content_ms=0.0 visited=46 neighbors_before=46 neighbors_after=45 avg_high=15.5 avg_low=7.0 avg_total=23.0 avg_after=22.5 additions=0
2026-02-06 17:14:54 INFO GraphStitch: query="How does BatchProcessor handle partial failures and implement at-least-once sema" cache_used=True cache_hits=44 cache_fallbacks=0 bfs_ms=0.2 entity_info_ms=11.7 content_ms=0.0 visited=47 neighbors_before=78 neighbors_after=55 avg_high=19.0 avg_low=8.5 avg_total=39.0 avg_after=27.5 additions=0
2026-02-06 17:15:55 INFO GraphStitch: query="How do all 5 optimizer rules combine with execution timing and plan caching in c" cache_used=True cache_hits=48 cache_fallbacks=0 bfs_ms=0.2 entity_info_ms=13.1 content_ms=0.0 visited=54 neighbors_before=110 neighbors_after=90 avg_high=29.0 avg_low=16.0 avg_total=55.0 avg_after=45.0 additions=0
```

## Findings
- Cache used on all queries: True
- Cache hits avg: 39.0 | cache fallbacks avg: 0.0
- BFS avg: 0.2 ms | entity_info avg: 9.3 ms | content avg: 0.0 ms
- Visited avg: 44.5 | neighbors before avg: 67.0 | after avg: 57.7
- Beam avg per hop: high 18.3, low 10.5, total 33.5 -> after 28.8
- Graph stitch additions total: 0

## Why No Speed Gain
- Graph stitch work is already sub-millisecond (BFS ~0.2 ms avg); it is not a dominant part of retrieval latency.
- Cache is used (cache_fallbacks=0), but cache load occurs per-process in `run_query.py`, so it does not amortize across queries in `run_experiment.py`.
- Beam pruning reduces neighbors modestly but expansions still add 0 entities, so no downstream context or ranking reduction occurs.

## Fix Suggestions
- Force cache reuse by running queries in a single long-lived process (e.g., keep `GraphTopology` in a service) so cache load cost amortizes.
- Reduce beam widths (`graph_stitch_beam_high`, `graph_stitch_beam_low`) if graph stitch starts adding entities; currently it adds none, so beam tuning won't impact latency.
- If retrieval latency is still high, focus on hybrid merge / expansion stages (outside graph stitch), which dominate wall time in telemetry.
