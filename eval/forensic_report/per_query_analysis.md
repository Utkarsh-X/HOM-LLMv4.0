# Per-Query Deep Analysis (Queries 3, 5, 8, 16, 18)

Evidence from `eval/runs/` responses and judge_results; telemetry where available.

---

## Query 3 — Optimizer rule conflict and priority order

**Query**: How does the query optimizer resolve conflicts between PREDICATE_PUSHDOWN and CONSTANT_FOLDING rules, and what is the priority order of the optimization rules?

### A. Context sufficiency

- **Run 20260124**: HOM-LLM answered that conflict resolution and priority order are “[not in context]”; only helper methods (e.g. `_is_constant_expression`) were cited. Judge: “Candidate claims the priority order information is not in the context.” **Conclusion**: Critical block (optimize method / rule sequence) was **missing or removed** in that run.
- **Runs 20260125, 20260127, 20260129**: Answers included correct rule order (Predicate → Projection → Constant Folding → Index Selection → Join Reordering) and sequential conflict resolution. Telemetry (run_20260129): 19 blocks, 3200 → 627 tokens after intelligence. **Conclusion**: Context **sufficient** in these runs; critical block was present and used.

### B. Answer utilization

- When context was sufficient, HOM-LLM **referenced** the correct components and order but **did not** provide a concrete example (e.g. “PREDICATE_PUSHDOWN runs first, then CONSTANT_FOLDING simplifies the result”). Cursor baseline quotes lines 81–98 and gives an illustrative example. **Conclusion**: Context was **used** for facts but **not** for example-level synthesis.

### C. Semantic coverage

- Sub-questions: (1) How are conflicts resolved? (2) Priority order?  
- HOM-LLM: (1) Answered when context present (“sequential order”); (2) Answered (full list). **Skipped/hedged**: Illustrative example; precise line refs (repeated “query_optimizer.py:1-208” or “1-50”).

### D. Structural vs semantic tradeoff

- HOM-LLM used “Component Interactions,” “Execution Trace,” “Summary” — **structure improved clarity**. Judge still preferred baseline for “concrete example” and “precise code references.” **Conclusion**: Structure helped; **completeness/depth** (example, refs) lagged.

### E. Cross-run

- **Meaningful variance**: Run 20260124 failed entirely (missing context); later runs correct but less complete than baseline. **Cause**: Context shift (retrieval/assembly/intelligence), not only reasoning.

**Confidence (findings)**: ≥ 0.8 (missing context in one run); 0.6–0.79 (underuse of context for examples/refs in others).

---

## Query 5 — L1/L2/L3 cache miss and cache promotion

**Query**: What happens when L1 memory, L2 Redis, and L3 database caches all miss, and how does cache promotion work?

### A. Context sufficiency

- **Run 20260124**: HOM-LLM stated the `get` method was not in context and described only `set`-based promotion. Judge: “Candidate incorrectly claims the `get` method … is not present.” **Conclusion**: **Missing context** for `get` in that run.
- **Runs 20260125, 20260127, 20260129**: Full miss path (L1 → L2 → fetch_func) and promotion (L2→L1, source→L1+L2) were explained. **Conclusion**: Context **sufficient** in these runs.

### B. Answer utilization

- When present, HOM-LLM used context correctly (get, set, _set_memory, fetch_func). Judge often preferred candidate for **clarity and structure** (Enumerated Components, line refs without large code blocks). **Conclusion**: Context **used well**; no critical block unused.

### C. Semantic coverage

- All sub-questions answered when context sufficient. No systematic skip or hedge.

### D. Structural vs semantic tradeoff

- Structure (headings, bullets) **improved** clarity without sacrificing completeness in later runs. **Conclusion**: No negative tradeoff here; HOM-LLM often **better** than baseline on clarity/verbosity.

### E. Cross-run

- **Variance**: One run (20260124) missing `get`; others complete. **Cause**: Context shift.

**Confidence**: ≥ 0.8 (missing context in one run); ≥ 0.8 (HOM-LLM advantage when context present).

---

## Query 8 — ConnectionPool when exhausted, wait/timeout

**Query**: How does ConnectionPool behave when all connections are in use and callers wait or time out?

### A. Context sufficiency

- All runs: Correct behavior (immediate `PoolExhaustedError`, no wait/timeout in `acquire`, `timeout` attribute unused). **Conclusion**: Context **sufficient** across runs.

### B. Answer utilization

- HOM-LLM referenced `acquire`, `_in_use`, `max_connections`, `PoolExhaustedError`, `timeout` correctly. Judge often preferred candidate for **conciseness** and **focus** (no “how to implement waiting”). **Conclusion**: Context **used well**.

### C.–E. Semantic coverage, tradeoff, cross-run

- Full coverage; structure helped; **stable across runs**. **Conclusion**: No capability gap; HOM-LLM often **improved** vs baseline.

**Confidence**: ≥ 0.8.

---

## Query 16 — BatchProcessor partial failures and at-least-once

**Query**: How does BatchProcessor handle partial failures and implement at-least-once semantics?

### A. Context sufficiency

- **Runs 20260124, 20260125, 20260127**: Answers described batch-level failure (try/except per batch, errors list, failed_count), `process` method, and that at-least-once is external (caller re-submit). Judge: “improved” or “baseline slightly more comprehensive” (idempotency). **Conclusion**: Context **sufficient**; `process` and batch-level behavior present.
- **Run 20260129**: HOM-LLM stated “the actual processing logic (e.g. process or run method) … is not present” and inferred **individual item** failure tracking. Judge: “Candidate incorrectly states that the actual processing logic is missing”; “candidate incorrectly infers individual item failures.” **Conclusion**: **Critical block (process method) missing or removed** in that run; model **mis-inferred** (item-level).

### B. Answer utilization

- When context included `process`: Correct batch-level description and external at-least-once. **Idempotency** and “external orchestrator” were mentioned less than in baseline.  
- Run 20260129: Wrong claim (“process missing”) and wrong inference (item-level); context **not** used for process method (either absent or unused).

### C. Semantic coverage

- When context good: Partial failures (batch-level) and at-least-once (external, caller) covered; idempotency/orchestrator **under-covered**.  
- Run 20260129: Core semantics **wrong** (item-level, process missing).

### D. Structural vs semantic tradeoff

- Structure was clear; in run_20260129 **semantic correctness** failed due to context/inference, not structure.

### E. Cross-run

- **Large variance**: Same query **correct** in three runs, **wrong** in one. **Cause**: Context shift (which blocks retained); reasoning then produced wrong inference when key block missing.

**Confidence**: ≥ 0.8 (context missing or over-trimmed in one run; wrong inference when thin).

---

## Query 18 — All 5 optimizer rules + execution timing + plan caching

**Query**: How do all 5 optimizer rules combine with execution timing and plan caching in complex queries?

### A. Context sufficiency

- **All HOM-LLM runs**: Answers either stated 4 of 5 rules “[not in context]” or gave a generic execution trace without full rule detail. Telemetry (run_20260129): **13 blocks**, 3200 → **511 tokens** after intelligence. **Conclusion**: **Insufficient or over-trimmed context** for all 5 rules + their effects; intelligence phase cut context heavily.

### B. Answer utilization

- HOM-LLM used plan cache, QueryPlanner, execution timing, and Constant Folding where present; **explicitly surrendered** on other rules (“[not in context]”). Cursor baseline explains all 5 rules and gives a concrete query lifecycle example. **Conclusion**: **Critical blocks for 4 rules absent or removed**; model did not invent; synthesis (example, “how they combine”) weaker.

### C. Semantic coverage

- Sub-questions: (1) All 5 rules? (2) Execution timing? (3) Plan caching? (4) How they combine?  
- HOM-LLM: (2)–(3) covered; (1) and (4) **incomplete** (only 1 rule in context, no full example). **Conclusion**: **Skipped/hedged** where context missing.

### D. Structural vs semantic tradeoff

- Long “Execution Trace” and component list added structure but **not** the missing rule details or integrated example. **Conclusion**: Structure did **not** compensate for **missing semantic content**.

### E. Cross-run

- **Consistent gap**: All runs (20260125, 20260127, 20260129) regressed on Q18; judge: “candidate states it lacks context for 4 of 5 rules.” **Cause**: **Consistent** context insufficiency or over-trimming for this multi-component query (13 blocks, 511 tokens after intelligence).

**Confidence**: ≥ 0.8 (context insufficient or over-trimmed); ≥ 0.8 (synthesis/example gap when context thin).

---

*End of Per-Query Analysis.*
