# Cursor Advantage Breakdown

Evidence-driven summary of where Cursor (baseline) is preferred over HOM-LLM in judge explanations and key_differences.

---

## 1. Advantages that recur across queries

| Advantage | Meaning | Queries | Confidence |
|-----------|---------|---------|------------|
| **Concrete examples** | Baseline provides an illustrative example (e.g. PREDICATE_PUSHDOWN then CONSTANT_FOLDING, or complex query lifecycle); candidate describes without example. | 3, 18 | ≥ 0.8 |
| **Precise code references** | Baseline “lines 81–98,” “54:102”; candidate “query_optimizer.py:1-208,” “connection.py:1-102.” | 3, 8, 16 | ≥ 0.8 |
| **Direct code quoting** | Baseline embeds relevant snippet; candidate “references line numbers” or “describes.” | 3, 5, 16 | ≥ 0.8 |
| **Synthesis beyond components** | Baseline explains idempotency, external orchestrator, “how at-least-once would be achieved externally”; candidate stays at “caller re-submit” or “not in context.” | 16, 18 | 0.6–0.79 |
| **Correct use of present context** | When baseline had code, it used it; in runs where HOM-LLM had thin context, it said “[not in context]” or mis-inferred. Cursor baseline is assumed to have had full codebase access. | 3, 5, 16, 18 | ≥ 0.8 (for HOM-LLM under thin context) |

---

## 2. Where HOM-LLM is preferred (no Cursor advantage)

| Aspect | Judge wording | Queries |
|--------|----------------|---------|
| **Structure / clarity** | “Candidate uses clear headings,” “Enumerated Components,” “more concise,” “easier to read.” | 5, 8 |
| **Verbosity** | “Candidate … lower verbosity,” “avoids large code blocks,” “references line numbers instead of embedding.” | 5, 8 |
| **Focus** | “Candidate directly answers … without extraneous information,” “avoids suggesting future implementations.” | 8 |

So Cursor’s advantages are **illustrative depth** (examples, quotes, precise refs) and **synthesis** (idempotency, orchestrator); HOM-LLM’s advantages are **structure** and **conciseness** when context is sufficient.

---

## 3. Cursor-specific behaviors (from judge key_differences)

- **Quotes the relevant code snippet** for rule order or method behavior.  
- **Provides a concrete example** to show how rules interact or how a complex query flows.  
- **Uses specific line ranges** (e.g. 81–98, 54:102) rather than file-wide (1–208).  
- **Discusses idempotency and external orchestrator** for at-least-once; **does not** stop at “caller must re-submit.”  
- **Identifies and explains all 5 optimizer rules** even when the prompt does not list them verbatim (inference from structure).  
- **Includes “how to implement” or “suggestions”** where the query is “how it behaves” (e.g. ConnectionPool); judge sometimes marks this as “beyond scope,” so not always an advantage.

---

## 4. Confidence

- **Certain (≥ 0.8)**: Concrete examples, precise refs, direct quoting, correct use of context (vs HOM-LLM surrender/mis-inference under thin context).  
- **Likely (0.6–0.79)**: Synthesis (idempotency, orchestrator); Cursor “infers all 5 rules” where HOM-LLM says “[not in context].”

---

*End of Cursor Advantage Breakdown.*
