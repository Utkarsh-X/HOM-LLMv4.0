# Problem 2 — Action & Remediation Layer Specification

## Status
**Freeze-ready.** This document captures the complete, stable understanding of Problem 2 and the action framework that builds *on top of* the frozen Problem‑1 diagnostic layer. No architectural mutation of Problem‑1 is required.

---

## 1. Purpose of Problem 2

Problem 2 exists to answer a single operational question:

> **Given a diagnosed context adequacy failure (from Problem‑1), what *corrective actions* are permissible, safe, and effective — without destabilizing the system or hiding failures?**

Problem‑2 does **not** diagnose. It **consumes diagnostics**.

It is the bridge between *knowing* something is wrong and *safely attempting to improve it*.

---

## 2. Non‑Goals (Explicitly Out of Scope)

Problem‑2 does **not**:
- Re‑classify intent
- Re‑interpret sufficiency
- Override vetoes
- Mutate Problem‑1 logic
- Introduce generative intelligence
- Optimize answers directly

All intelligence here is **procedural and bounded**.

---

## 3. Inputs from Problem‑1 (Contract)

Problem‑2 only reacts to structured signals emitted by Problem‑1:

### Required Fields
- `final_label` ∈ {ALIGNED, PARTIALLY_ALIGNED, MISALIGNED}
- `deciding_factor` (single strongest veto / downgrade)
- `intent_class`
- `failed_axes[]`
- `negative_evidence[]`
- `confidence`
- `fragility_flag`

Problem‑2 **must not infer missing information**. If a field is absent, default behavior is *no action*.

---

## 4. Action Philosophy

### Core Rule
> **Problem‑2 may only attempt actions that directly address the diagnosed failure axis.**

No speculative retries. No blind expansion. No generic fixes.

### Safety Invariants
- Every action must be reversible
- Every action must be attributable to a diagnostic signal
- Every action must be logged with cause → effect mapping

---

## 5. Action Classes

### 5.1 Retrieval‑Level Actions

Triggered by:
- Structural absence
- Missing abstraction level
- Wrong dominant subsystem

Examples:
- Expand retrieval scope upward (e.g., include README / docs)
- Include parent directories / modules
- Include cross‑component references

Constraints:
- No chunk deletion
- No relevance re‑ranking heuristics here

---

### 5.2 Token Budget Actions

Triggered by:
- Context fragmentation
- Over‑compression
- PARTIALLY_ALIGNED with high diversity

Examples:
- Increase token ceiling for next retrieval
- Allow multi‑pass context assembly

Constraints:
- Must not reduce context
- Must not violate global cost caps

---

### 5.3 Prompt Strategy Actions

Triggered by:
- Structural adequacy but explanation gap

Examples:
- Switch explanation style ("overview first")
- Require examples or diagrams (textual)

Constraints:
- Prompt change must be logged
- Prompt must not claim missing info is present

---

### 5.4 Retry / Escalation Actions

Triggered by:
- Historical fragility
- Repeated MISALIGNED outcomes

Examples:
- Retry with expanded constraints
- Surface partial answer + warning
- Defer to agent / human review (future)

Constraints:
- Maximum retry count
- Must degrade gracefully

---

## 6. Action Selection Matrix

Actions are selected via **deterministic mapping**, not scoring.

| Deciding Factor | Allowed Actions |
|----------------|----------------|
| Structural Absence | Retrieval Expansion |
| Fragmentation | Token Budget Increase |
| Wrong Subsystem | Retrieval Re‑target |
| Explanation Gap | Prompt Strategy |
| Historical Fragility | Retry Cap / Escalation |

If no mapping exists → **no action**.

---

## 7. Ordering & Limits

1. Structural fixes first
2. Token fixes second
3. Prompt adjustments last

Never apply more than **one action per axis per run**.

---

## 8. Observability & Logging

Each action emits:
- `action_type`
- `trigger_signal`
- `expected_effect`
- `actual_outcome` (post‑hoc)

This enables offline evaluation without online learning.

---

## 9. Failure Safety

If actions fail to improve alignment:
- System must return original answer + diagnostic warning
- Never silently retry indefinitely

Failure must be **visible**, not masked.

---

## 10. Why Problem‑2 Is Stable

- Fully downstream of diagnostics
- No feedback loops
- No adaptive learning
- No intelligence inflation

Removing Problem‑2 leaves Problem‑1 intact.

---

## 11. Readiness Statement

Problem‑2 is **architecturally complete**.

It can be implemented incrementally, action‑by‑action, without modifying Problem‑1.

No further conceptual questions are required to proceed.

---

## 12. Closure

With Problem‑1 frozen and Problem‑2 specified:
- The system can *detect*, *explain*, and *attempt correction* safely
- Future improvements are supported without re‑architecture

This completes the foundation phase.

