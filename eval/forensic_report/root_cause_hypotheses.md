# Root Cause Hypotheses (Ranked by Confidence)

Diagnosis only; no fixes or redesign.

---

## 1. Ranked hypotheses

| Rank | Hypothesis | Type | Confidence | Evidence |
|------|------------|------|------------|----------|
| 1 | **Critical blocks missing or removed before generation** (retrieval, ranking, or intelligence-phase trimming) | Contextual / Architectural | ≥ 0.8 | Q3/Q5 run_20260124: “[not in context],” “get not present.” Q16 run_20260129: “process not present.” Q18: “4 of 5 rules not in context”; telemetry 13 blocks, 511 tokens after intelligence. |
| 2 | **Intelligence phase reduces context below sufficiency for multi-component queries** | Contextual / Architectural | ≥ 0.8 | Telemetry: context_tokens_after 511–627 for Q3, Q16, Q18 (from 3200). Same phase applies actions and can remove/suppress blocks; heavy reduction correlates with incomplete or wrong answers. |
| 3 | **HOM-LLM surrenders or mis-infers when context is thin** (no wait/retry; wrong inference) | Behavioral / Reasoning | ≥ 0.8 | Explicit “[not in context]”; Q16 run_20260129 wrong inference (item-level failure, process missing). Cursor baseline (full codebase) does not face same thin context. |
| 4 | **HOM-LLM favors structure over illustrative depth** (examples, precise refs, idempotency/orchestrator synthesis) | Behavioral / Presentation | 0.6–0.79 | Judge: baseline “concrete example,” “lines 81–98,” “idempotency”; candidate “describes,” “query_optimizer.py:1-208,” “touches upon.” Repeated across Q3, Q16. |
| 5 | **Fixed token budget (3200) + ranking/assembly** can leave multi-file or multi-rule queries with too few blocks | Architectural | 0.6–0.79 | Q18: 13 blocks for “all 5 rules + timing + plan cache”; query spans optimizer, planner, execution engine. Single-file queries (Q8) stable. |
| 6 | **Retrieval/ranking non-determinism or query-dependent quality** causes run-to-run context variance | Contextual / Architectural | 0.6–0.79 | Same query (Q16) correct in three runs, wrong in one; no code change between runs. Suggests retrieval or ranking variance. |
| 7 | **Prompt or instructions encourage “do not guess”** so model says “[not in context]” instead of inferring | Prompt-level / Behavioral | 0.4–0.59 | Plausible from behavior; no direct prompt inspection in scope. |
| 8 | **Judge prefers code quotes and examples** so HOM-LLM penalized for structure-only answers even when correct | Evaluation | 0.4–0.59 | Judge text repeatedly values “code snippet,” “concrete example”; could over-penalize structured, reference-only correct answers. |

---

## 2. What is missing vs weaker (summary)

- **Missing**: In some runs, **blocks containing** the rule order (Q3), `get` (Q5), `process` (Q16), or full optimizer rule set (Q18) were **not** in the final context. So **missing context** (retrieval/assembly/trimming).
- **Weaker**: When context **is** sufficient, HOM-LLM still **underuses** it for examples, precise line refs, and synthesis (idempotency, orchestrator). So **weaker synthesis/presentation**, not missing facts.

---

## 3. Architectural vs behavioral vs prompt-level

| Hypothesis | Architectural | Behavioral | Prompt-level |
|------------|---------------|------------|--------------|
| 1 (blocks missing/removed) | Yes | — | — |
| 2 (intelligence trims too much) | Yes | — | — |
| 3 (surrender / wrong inference) | — | Yes | — |
| 4 (structure vs depth) | — | Yes | Possible |
| 5 (token budget + assembly) | Yes | — | — |
| 6 (retrieval variance) | Yes | — | — |
| 7 (“do not guess”) | — | Yes | Yes |
| 8 (judge preference) | — | — | — (evaluation) |

---

*End of Root Cause Hypotheses.*
