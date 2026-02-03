# Capability Gap Matrix

**Focus queries**: 3, 5, 8, 16, 18. **Runs**: run_20260124_143034, run_20260125_091434, run_20260127_084123, run_20260129_134226.

---

## 1. Capability vs Cursor (what is missing vs weaker)

| Capability | Missing | Weaker | Evidence | Confidence |
|------------|---------|--------|----------|------------|
| **Concrete examples** (e.g. rule interaction) | No | Yes | Judge: baseline “concrete example”; candidate “lacks.” Q3, Q18. | ≥ 0.8 |
| **Precise code references** (line ranges) | No | Yes | Judge: baseline “lines 81–98”; candidate “query_optimizer.py:1-208.” | ≥ 0.8 |
| **Direct code quoting** in explanation | No | Yes | Judge: baseline “directly quotes”; candidate “describes.” | ≥ 0.8 |
| **Synthesis beyond components** (idempotency, orchestrator) | Partial | Yes | Judge: baseline “idempotency,” “external orchestrator”; candidate “touches upon,” “omits.” Q16. | 0.6–0.79 |
| **Answering when context is partial** (infer “all 5 rules”) | Yes (behavior) | — | Q18: candidate “[not in context]” for 4/5 rules; baseline explains all 5. | 0.6–0.79 |
| **Correct use of present context** (no wrong inference) | No (fails in some runs) | — | Q16 run_20260129: candidate “processing logic not present,” item-level failure; baseline correct (batch-level). | ≥ 0.8 |
| **Structural clarity** (Enumerated Components, etc.) | — | No (HOM-LLM often better) | Judge: candidate “clear headings,” “more concise”; baseline “large code blocks.” Q5, Q8. | ≥ 0.8 |

---

## 2. Per-query gap summary (judge verdicts and scores)

| Query | Run 20260124 | Run 20260125 | Run 20260127 | Run 20260129 | Primary gap |
|-------|----------------|--------------|--------------|--------------|-------------|
| **3** | Regressed (1/1/1) | Improved (5/3) | Improved (4/4) | Mixed (4/4 vs regressed) | Missing/weak context in 20260124; elsewhere lack of example + precise refs. |
| **5** | Regressed (1/1/1) | Improved | Improved (5/5) | Improved | Missing context in 20260124 (“get not present”); later runs HOM-LLM often wins. |
| **8** | Improved | Improved | Improved | Improved | No consistent gap; HOM-LLM often preferred (concise, structured). |
| **16** | Improved (5/5) | Improved (5/4) | Improved (5/3) | Regressed (2/2) | Run 20260129: wrong inference + “process missing”; other runs correct. |
| **18** | (no Q18) | Regressed (2/2) | Regressed (3/2) | Regressed (3/2) | “[not in context]” for 4/5 rules; no concrete example; thin/trimmed context. |

---

## 3. Gap type classification

| Gap | Architectural | Reasoning | Contextual | Presentation |
|-----|---------------|-----------|------------|---------------|
| Missing/over-trimmed context (Q3, Q5, Q16, Q18 in some runs) | Yes (budget, intelligence phase) | — | Yes | — |
| “[not in context]” / surrender | — | Yes | Yes (triggered by thin context) | — |
| Wrong inference (Q16 run_20260129) | — | Yes | Yes (thin context) | — |
| No example / broad refs | — | Yes | — | Yes |
| Lack of idempotency/orchestrator synthesis | — | Yes | — | — |
| Structural clarity (HOM-LLM advantage) | — | — | — | Yes |

---

## 4. How close is HOM-LLM to Cursor (capability-wise)?

- **When context is sufficient and retained**: HOM-LLM is **close** — same model (Gemini 2.5 Flash), correct facts, often better structure and conciseness (Q5, Q8). Remaining gap is **illustrative depth** (examples, precise refs, synthesis).
- **When context is insufficient or over-trimmed**: HOM-LLM **falls behind** — surrender (“[not in context]”) or wrong inference; Cursor baseline is assumed to have had full codebase access, so not directly comparable on “context.”
- **Summary**: Capability-wise, HOM-LLM is **close** under good context; **fragile** under variable context. The gap is **not primarily “model is weaker”** but **context sufficiency + retention + reasoning style under uncertainty**.

---

*End of Capability Gap Matrix.*
