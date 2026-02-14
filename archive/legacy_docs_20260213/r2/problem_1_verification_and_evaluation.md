# Problem 1: Intent-Gated Sufficiency Layer — Verification & Evaluation

## Verification Checklist (Completed)

### 1. Intent gating works

- **Mandatory axes change correctly per intent**
  - `ARCHITECTURAL`: `mandatory_axes = ("STRUCTURAL", "SEMANTIC")`, `early_exit_allowed = False` (see `intent.py`: `_ARCHITECTURAL_PATTERNS` → `IntentResult`).
  - `BEHAVIORAL`: `mandatory_axes = ("RULE", "SEMANTIC")`, `early_exit_allowed = True`.
  - `IMPLEMENTATION`: `mandatory_axes = ("RULE", "STRUCTURAL", "SEMANTIC")`, `early_exit_allowed = True`.
  - `UNKNOWN`: `mandatory_axes = ("STRUCTURAL", "RULE", "SEMANTIC")`, `early_exit_allowed = False` (conservative).
- **Early exit is disabled for architectural/system intents**
  - `ARCHITECTURAL` and `UNKNOWN` set `early_exit_allowed = False`. Pipeline does not implement early-exit branching (all signals always run); the flag is auditable only.

### 2. Veto logic is conjunctive

- **One hard failure blocks SUFFICIENT**
  - `veto.py`: For each axis in `_HARD_VETO_ORDER` (STRUCTURAL, RULE) that is mandatory, if `label == "INSUFFICIENT"` then `final_verdict = "INSUFFICIENT"` and `deciding_factor = axis`; loop breaks. No averaging.
- **No signal can override a hard veto**
  - Only STRUCTURAL and RULE are hard vetoes. Semantic is soft veto only (plan §6.1). A high semantic score cannot change INSUFFICIENT when structural or rule has already vetoed.

### 3. Structural signal authority

- **Structural insufficiency produces a hard veto when mandatory**
  - When intent is ARCHITECTURAL or IMPLEMENTATION or UNKNOWN, STRUCTURAL is mandatory. If `signals["structural"].label == "INSUFFICIENT"`, `resolve_veto` sets `final_verdict = "INSUFFICIENT"`, `deciding_factor = "STRUCTURAL"`.
- **Semantic strength alone cannot pass architectural queries**
  - For ARCHITECTURAL, both STRUCTURAL and SEMANTIC are mandatory. Structural is checked first as hard veto; if structural fails, verdict is INSUFFICIENT regardless of semantic score.

### 4. Auditability

- **Each signal emits `{score, label}`**
  - `SignalResult(score=..., label=...)`; `SufficiencyResult.to_dict()` emits `"signals": { "semantic": {"score": ..., "label": ...}, "rule": ..., "structural": ... }`.
- **Final output includes `deciding_factor`**
  - `SufficiencyResult.deciding_factor` is set to the first axis that caused a hard veto, or SEMANTIC for soft veto (PROBABLY_SUFFICIENT), or None when SUFFICIENT. Emitted in `to_dict()`.

### 5. Read-only safety

- **No side-effects on existing pipeline**
  - `run_sufficiency(query, context_artifact, embedder)` only reads `query` and `context_artifact` (and optionally calls `embedder.embed_query` / `embedder.embed_code`). It does not modify context, retrieval, ranking, or prompts.
- **Safe to toggle off without changing behavior**
  - This layer is not invoked by the runtime in this implementation. When integrated, callers can skip `run_sufficiency`; no other component depends on it. Disabling it does not alter generation, retrieval, or ranking.

---

## Constraints Enforced

| Constraint | Status |
|------------|--------|
| No LLM calls | ✅ Intent is rule-based keywords only; signals use embedder (frozen encoder) or deterministic overlap. |
| No prompt rewriting or context shrinking/expansion | ✅ Layer only reads context; does not modify it. |
| No ranking, reranking, or retrieval modification | ✅ Read-only. |
| No probabilistic voting or averaging | ✅ Veto is conjunctive (AND); no averaging of scores for final verdict. |
| Deterministic or bounded-learning signals only | ✅ All signals are deterministic (thresholds fixed). Learned advisor not implemented (optional). |
| Explicit veto hierarchy (AND-logic) | ✅ `resolve_veto` applies STRUCTURAL then RULE as hard vetoes; SEMANTIC soft only. |
| Read-only diagnostics | ✅ Output is verdict + attribution only. |
| Fully auditable outputs | ✅ `to_dict()` matches plan §7 contract. |
| Conservative default | ✅ UNKNOWN intent → all axes mandatory; empty context → INSUFFICIENT; no embedder → semantic INSUFFICIENT. |

---

## Evaluation: Does this layer directly address previously observed failures?

**Answer: Yes.**

Previously observed failures (from forensic report) were:

1. **Context sufficiency loss** — Answers wrong or “[not in context]” when critical blocks were missing or removed (e.g. Q3, Q5 run_20260124; Q16, Q18 run_20260129).
2. **Abstraction mismatch** — Wrong level of explanation (e.g. item-level vs batch-level for BatchProcessor).
3. **Surrender after shrinking** — Model said “[not in context]” after intelligence phase trimmed context heavily (e.g. Q18: 13 blocks, 511 tokens after intelligence).

This layer **directly addresses** them by **diagnosing and attributing**, not by fixing:

- **Context sufficiency loss**: When retrieved/assembled context is thin or missing key entities, **semantic** (centroid/diversity), **rule** (term overlap), and **structural** (code blocks, symbols, files) signals drop. If mandatory axes fail, verdict is **INSUFFICIENT** and **deciding_factor** identifies which axis (e.g. STRUCTURAL or RULE). Downstream policy can then block confident answering, trigger re-retrieval, or show an explicit insufficiency message — without this layer performing recovery.
- **Abstraction mismatch**: **Structural** signal (code blocks, symbols, distinct files) and **rule** signal (entity overlap) help detect when context lacks the right abstraction (e.g. no code for implementation queries). For ARCHITECTURAL intent, structural insufficiency causes a **hard veto**, so semantic strength alone cannot pass.
- **Surrender after shrinking**: If the intelligence phase (or any step) shrinks context below sufficiency, the layer run **after** context assembly would see the **final** context. Low block count, low token count, and missing terms would produce INSUFFICIENT or PROBABLY_SUFFICIENT with a clear **deciding_factor**. That gives a machine-readable explanation of *what is missing* instead of silent surrender; recovery (re-retrieval, user message, conservative mode) remains policy-driven, outside this layer.

So the layer **directly addresses** these failures by **measuring sufficiency and attributing failure**, enabling controlled recovery rather than silent failure. It does not implement recovery itself (as required).

---

*End of Verification and Evaluation.*
