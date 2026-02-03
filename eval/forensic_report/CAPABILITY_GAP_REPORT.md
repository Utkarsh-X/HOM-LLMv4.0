# HOM-LLM Capability Forensic Analysis — Capability Gap Report

**Classification**: Diagnosis only. No fixes, optimization, or redesign. No alignment evaluation.

**Scope**: Queries 3, 5, 8, 16, 18; runs in `eval/runs/` (run_20260124_143034, run_20260125_091434, run_20260127_084123, run_20260129_134226); comparison to `cursor_baseline.json`.

---

## 1. Executive Summary (≤1 page)

See **[executive_summary.md](executive_summary.md)** for full text. Summary:

- **Capability-wise**: HOM-LLM is **close to Cursor** when the right context is assembled and retained; on Q5 and Q8 it often **matches or beats** Cursor. Gaps appear when context is **missing or over-trimmed** (retrieval/assembly/intelligence) or when the model **surrenders** (“[not in context]”) or **mis-infers** (e.g. Q16 run_20260129).
- **Why scores lag**: (1) **Incomplete or wrong answers** in some runs (missing/wrong context). (2) **Missing illustrative depth** (examples, precise line refs, idempotency/orchestrator synthesis) even when facts are correct.
- **Main finding**: Gaps are **context sufficiency and retention** + **reasoning style under uncertainty** (surrender or wrong inference) + **weaker synthesis/presentation** (structure vs examples/refs). Not primarily “weaker model.”

---

## 2. Capability Gap Matrix

See **[capability_gap_matrix.md](capability_gap_matrix.md)**.

- **Missing vs weaker**: Missing = critical blocks absent or removed (Q3, Q5, Q16, Q18 in some runs). Weaker = no example, broad refs, less synthesis when context is present.
- **Per-query summary**: Q3/Q5 variable (one run missing context); Q8 stable (no gap); Q16 one severe regression (wrong inference + “process missing”); Q18 consistently behind (“[not in context]” for 4/5 rules).
- **Gap types**: Contextual/architectural (budget, intelligence phase, retrieval); reasoning (surrender, wrong inference); presentation (examples, refs).

---

## 3. Per-Query Deep Analysis

See **[per_query_analysis.md](per_query_analysis.md)**.

- **Q3**: Context missing in run_20260124; in other runs context used for facts but not for example or precise refs.
- **Q5**: Context missing in run_20260124 (“get not present”); later runs HOM-LLM often preferred.
- **Q8**: No gap; HOM-LLM often preferred (concise, structured).
- **Q16**: Correct in three runs (batch-level, process method); run_20260129 wrong (“process missing,” item-level) — context or trimming.
- **Q18**: All runs; context insufficient or over-trimmed (13 blocks, 511 tokens); “[not in context]” for 4/5 rules; no full example.

---

## 4. Cross-Run Consistency Findings

See **[cross_run_consistency.md](cross_run_consistency.md)**.

- **Meaningful variance**: Q3, Q5, Q16 (same query correct in some runs, wrong or incomplete in others). Q18 stably weak.
- **Cause**: **Context shift** (which blocks retrieved and retained), not only reasoning. Reasoning reacts (surrender or wrong inference when thin).

---

## 5. Cursor Advantage Breakdown

See **[cursor_advantage_breakdown.md](cursor_advantage_breakdown.md)**.

- **Cursor**: Concrete examples, precise code refs, direct quoting, synthesis (idempotency, orchestrator), inferring “all 5 rules” from structure.
- **HOM-LLM (when context good)**: Better structure, conciseness, clarity; weaker on examples and synthesis.

---

## 6. Root Cause Hypotheses (ranked by confidence)

See **[root_cause_hypotheses.md](root_cause_hypotheses.md)**.

| Rank | Hypothesis | Confidence |
|------|------------|------------|
| 1 | Critical blocks missing or removed (retrieval/ranking/intelligence) | ≥ 0.8 |
| 2 | Intelligence phase reduces context below sufficiency for multi-component queries | ≥ 0.8 |
| 3 | HOM-LLM surrenders or mis-infers when context is thin | ≥ 0.8 |
| 4 | HOM-LLM favors structure over illustrative depth (examples, refs, synthesis) | 0.6–0.79 |
| 5 | Fixed token budget + assembly leaves multi-rule queries with too few blocks | 0.6–0.79 |
| 6 | Retrieval/ranking variance causes run-to-run context shift | 0.6–0.79 |
| 7 | Prompt encourages “do not guess” → “[not in context]” | 0.4–0.59 |
| 8 | Judge prefers code quotes and examples | 0.4–0.59 |

---

## 7. System Readiness Assessment

- **Sound**: No — capability is **context-dependent**; same query can be correct or wrong across runs.
- **Fragile**: Yes — when context is sufficient and retained, HOM-LLM is close to or ahead on clarity/structure; when context is insufficient or over-trimmed, answers degrade or become wrong.
- **Unclear**: Partially — root causes are identified with high confidence (context + reasoning under uncertainty); exact retrieval/ranking/intelligence behavior per run was not re-executed.

**Verdict**: **Fragile.** Reinforce (context sufficiency, retention), simplify (e.g. intelligence aggressiveness), or surgically extend (e.g. multi-rule context budget) — do not blindly iterate.

---

## 8. Confidence and evidence standards

- **≥ 0.8 (Certain)**: Strong evidence across runs (missing context, surrender/mis-inference, intelligence trim, Cursor examples/refs).
- **0.6–0.79 (Likely)**: Repeated but not universal (synthesis gap, token budget, retrieval variance).
- **0.4–0.59 (Possible)**: Weak or single-instance (prompt “do not guess,” judge preference).
- **< 0.4**: Not claimed.

---

## 9. Explicit statements (as required)

- **What is missing**: In some runs, **blocks** containing rule order (Q3), `get` (Q5), `process` (Q16), or full 5-rule set (Q18) were **not** in the final context (missing or removed).
- **What is weaker**: When context **is** present, **examples**, **precise line refs**, and **synthesis** (idempotency, orchestrator) are weaker than Cursor.
- **How close capability-wise**: **Close** under good context (same model; correct facts; often better structure). **Not close** under bad context (surrender or wrong inference). So **close but fragile**.

---

*End of Capability Gap Report. This report is for architectural decision-making, not feature development.*
