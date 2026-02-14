# Quick Analysis - run_20260204_145217

## Query 16 - BatchProcessor "not in context"
- **Run ID:** `3b4314a7-929d-4081-bb18-ebccb8bf020f`
- **Retrieval candidates:** 22 (bm25=28, vector=50, merged=22)
- **Top blocks (L1, first 10):**
  - `expanded:48dc8273aeda9734:_compute_file_hash:77`
  - `expanded:48dc8273aeda9734:_chunk_text:160`
  - `a6ac4d259ba1c6d9:63da6f3aee15a71a:BatchResult:16`
  - `6157ae2fab7f3e72:fb33a4cc9fd84c4f:PlanStep:23`
  - `917a698e6a439c13:d2d702128434f5f6:search:16`
  - `b6102d15ada8b151:0b6527fa31d2c936:SearchError:6`
  - `50b9c9036fa9a01c:eccbae45cfb8942a:OptimizedQuery:252`
  - `c291241be1820c9d:a8906207801e422c:RedisClient:17`
  - `50b9c9036fa9a01c:eccbae45cfb8942a:improvement_ratio:260`
  - `50b9c9036fa9a01c:eccbae45cfb8942a:_get_index_benefit:217`
- **Diagnostics:** P1=INSUFFICIENT, P2 actions = `RETRIEVAL_RE_TARGET`, `TOKEN_BUDGET_INCREASE`
- **Index check:** `BatchProcessor` **exists** in index (`async_jobs\batch_processor.py`, symbol_id `63da6f3aee15a71a:BatchProcessor:26`), but it **did not appear** in the top context blocks.
- **Why the model said "not in context":** The final context included `BatchResult` but **not** `BatchProcessor`, so the answer correctly refused the missing implementation despite it existing in the corpus.

**Subtle fix:** add a targeted symbol backfill rule for `BatchProcessor` when query mentions it (or lower MMR penalty for class name matches). Also consider wiring P2 `RETRIEVAL_RE_TARGET` to actually re-run retrieval/assembly.

## Query 18 - PARTIAL response
- **Run ID:** `4373438f-6b7c-4e03-9a4e-e2d3bd339d11`
- **Generation telemetry:** `finish_reason = max_tokens` (status=PARTIAL)

**Config tweak:** raise `generation.max_output_tokens` to **12000** to reduce truncation on long multi-rule explanations.

## Short Recommendations
- **Retrieval/backfill:** add symbol backfill for explicitly named classes (e.g., `BatchProcessor`) or reduce MMR diversity penalty for exact-name matches.
- **P2 execution:** enable real execution of `RETRIEVAL_RE_TARGET` (not just logging) so missing symbols are pulled in.
- **Generation length:** set `generation.max_output_tokens: 12000` to avoid PARTIAL on long answers.
