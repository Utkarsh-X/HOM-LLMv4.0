# HOM-LLM Capability Forensic Analysis — Executive Summary

**Purpose**: Truth-seeking, non-invasive diagnostic of HOM-LLM(v2.0) vs Cursor. No fixes, optimization, or redesign.

**Scope**: Queries 3, 5, 8, 16, 18 across runs in `eval/runs/` (run_20260124_143034, run_20260125_091434, run_20260127_084123, run_20260129_134226); comparison to `cursor_baseline.json`.

---

## 1. Bottom line

- **Capability-wise**: HOM-LLM is **close to Cursor** when the right context is assembled and retained. On queries 5 and 8 it often **matches or beats** Cursor (clarity, structure, conciseness). Gaps appear when (a) critical context is missing or removed before generation, or (b) the model surrenders with “[not in context]” or mis-infers from thin context.
- **Why scores lag**: Judge penalties cluster on **incomplete or wrong answers** (Q3, Q5, Q16, Q18 in some runs) and on **missing illustrative depth** (examples, precise line refs, idempotency/orchestrator synthesis) even when the answer is factually correct.
- **Main finding**: Gaps are **not primarily architectural** in the sense of “wrong pipeline.” They are driven by **context sufficiency and retention** (retrieval/ranking/context assembly and intelligence-phase trimming), **reasoning style** (structure vs synthesis/examples), and **behavior under uncertainty** (surrender or wrong inference vs Cursor’s more assertive use of context).

---

## 2. What Cursor does that HOM-LLM often does not

| Capability | Evidence | Confidence |
|------------|----------|------------|
| **Concrete examples** (e.g. PREDICATE_PUSHDOWN then CONSTANT_FOLDING) | Judge repeatedly: baseline “provides a concrete example”; candidate “lacks” it. | ≥ 0.8 |
| **Precise code references** (e.g. lines 81–98 vs 1–208) | Judge: baseline “more precise code references”; candidate “very broad (e.g. query_optimizer.py:1-208)”. | ≥ 0.8 |
| **Synthesis beyond components** (idempotency, external orchestrator for at-least-once) | Judge: baseline “idempotency,” “external orchestrator”; candidate “touches upon but doesn’t elaborate.” | 0.6–0.79 |
| **Answering fully when context is partial** (infer “all 5 rules” from structure) | Q18: baseline “identifies and explains all 5 rules”; candidate “explicitly states it lacks context for 4 of 5.” | 0.6–0.79 |
| **Direct code quoting** in explanation | Judge: baseline “directly quotes the relevant code snippet”; candidate “describes it.” | ≥ 0.8 |

---

## 3. Why gaps appear (causes)

- **Missing context**: In run_20260124 (Q3, Q5) and run_20260129 (Q16, Q18), answers claimed “[not in context]” or “processing logic not present.” Telemetry shows heavy intelligence-phase trimming (e.g. Q18: 3200 → 511 tokens, 13 blocks). So **critical blocks were absent or removed** in those runs. **Confidence: ≥ 0.8**
- **Context present but underused**: When context is sufficient (e.g. Q3 in run_20260127/20260129), HOM-LLM gives correct rule order and conflict resolution but **omits examples and precise line refs**. So **weaker synthesis/presentation**, not missing facts. **Confidence: 0.6–0.79**
- **Weak synthesis across components**: Cursor explains “how at-least-once is achieved externally” and “idempotency”; HOM-LLM often stays at “caller must re-submit” without tying to design. **Confidence: 0.6–0.79**
- **Over-defensive generation**: Model explicitly says “[not in context]” or “processing logic not present” when context is thin; in one run (Q16 run_20260129) it also **mis-infers** (item-level failure tracking). So **hedging/surrender** and **occasional wrong inference** under uncertainty. **Confidence: ≥ 0.8**
- **Structure vs semantic depth**: HOM-LLM’s “Enumerated Components / Component Interactions / Summary” improves clarity; judge still prefers baseline for “concrete example,” “code snippet,” “deeper implications.” So **structural clarity sometimes at the cost of completeness/depth**. **Confidence: 0.6–0.79**

---

## 4. Cross-run consistency

- **High variance by run**: Same query (e.g. Q16) can be **correct and nearly complete** (run_20260124, 20260125, 20260127) or **wrong and incomplete** (run_20260129: “process missing,” item-level inference). Cause is **context shift** (which blocks are retrieved and retained), not only reasoning. **Confidence: ≥ 0.8**
- **Stable strengths**: Q5 and Q8 are **consistently improved or on par** across runs when context includes the relevant code (get method, acquire method). So when context is sufficient, HOM-LLM’s structure and conciseness are a net plus.

---

## 5. Failure taxonomy (architectural vs behavioral vs prompt-level)

- **Contextual (operational/architectural)**: Fixed token budget (3200), intelligence phase that can remove blocks, retrieval/ranking that varies by run. **Missing or over-trimmed context** is a structural factor. **Confidence: ≥ 0.8**
- **Reasoning/behavioral**: Preference for enumeration and hedging (“[not in context]”), less use of examples and code quotes, occasional wrong inference when context is thin. **Confidence: ≥ 0.8**
- **Presentation**: Broad line refs, bulletization without illustrative examples. Could be prompt-level or model behavior. **Confidence: 0.6–0.79**

---

## 6. System readiness

- **Assessment**: **Fragile** — capability is **context-dependent**. When the right blocks are present and retained, HOM-LLM is close to or ahead of Cursor on clarity and structure. When context is insufficient or over-trimmed, answers degrade or become wrong. No change to prompts, architecture, or alignment was made; this is diagnosis only.

---

*End of Executive Summary.*
