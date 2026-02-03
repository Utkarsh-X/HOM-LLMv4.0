# Problem 1 – Intent‑Gated Sufficiency Layer (Architectural & Action Plan)

This document defines **the first completed intelligence layer** of the HLLM system: the **Intent‑Gated Sufficiency Layer**.  
It is deliberately scoped, deterministic, read‑only, and auditable. It does **not** modify generation directly. It decides *whether the system is allowed to answer confidently* and *what must be present before answering*.

---

## 1. Purpose (Why This Layer Exists)

This layer exists to solve one specific class of failures:

> **Answers that are semantically fluent but structurally or contextually incomplete.**

Observed symptoms it addresses:
- Context sufficiency failure (not enough information to answer properly)
- Context distortion (wrong abstraction level)
- Cross‑run instability caused by context variability
- Model surrender (“not in context”) after aggressive shrinking
- Structural explanation gaps (answer without explanation)

This layer **does not**:
- Rank answers
- Rewrite prompts
- Shrink context
- Perform reasoning
- Override generation

It only **measures, gates, and explains sufficiency**.

---

## 2. Design Constraints (Non‑Negotiable)

These constraints are intentional and enforced:

- ❌ No LLM calls
- ❌ No generation or prompt mutation
- ❌ No probabilistic voting between signals
- ❌ No single authority component
- ❌ No averaging for final decisions

- ✅ Deterministic or bounded‑learning only
- ✅ Explicit veto hierarchy
- ✅ Machine‑readable outputs
- ✅ Loggable failure attribution
- ✅ Safe default: conservative over permissive

---

## 3. Conceptual Model

### 3.1 Core Principle

**Sufficiency is conjunctive, not additive.**  
All *mandatory* requirements must pass. A single critical failure vetoes sufficiency.

This layer answers:
> *“Do we have the minimum information required to answer this query correctly?”*

Not:
- “Can we guess?”
- “Is this probably fine?”

---

## 4. High‑Level Architecture

```
Query
  ↓
Intent Classifier (non‑LLM)
  ↓
Required Signal Set Selection
  ↓
Parallel Sufficiency Signals
  ├─ Semantic Coverage (embeddings)
  ├─ Rule / Entity Coverage
  ├─ Structural Coverage (code‑aware)
  ├─ Learned Advisor (optional, bounded)
  ↓
Veto Resolution (AND‑logic)
  ↓
Final Sufficiency Verdict + Attribution
```

---

## 5. Intelligence Components (What “Intelligence” Means Here)

### 5.1 Query Intent Classifier (Mandatory)

**Purpose:** Determine *which sufficiency axes are mandatory* for this query.

**Implementation (non‑LLM):**
- Rule‑based keyword patterns (architectural vs implementation vs behavioral)
- Lightweight embedding cluster classification (frozen encoder)
- Metadata hints (symbol names, file references)

**Output:**
```json
{
  "intent": "ARCHITECTURAL",
  "mandatory_axes": ["STRUCTURAL", "SEMANTIC"],
  "early_exit_allowed": false
}
```

This component is the *root intelligence*. Everything else depends on it.

---

### 5.2 Semantic Coverage Signal

**Purpose:** Ensure retrieved context semantically aligns with the query.

**Mechanism:**
- Query embedding vs context centroid similarity
- Diversity / spread of context embeddings

**Strength:** Fast, general‑purpose
**Weakness:** Cannot detect abstraction mismatch

**Never authoritative alone.**

---

### 5.3 Rule / Entity Coverage Signal

**Purpose:** Detect missing concrete elements (terms, entities, components).

**Mechanism:**
- Query term extraction
- N‑gram / identifier / entity overlap

**Strength:** Deterministic, interpretable
**Weakness:** Coarse

---

### 5.4 Structural Coverage Signal (Code‑Aware)

**Purpose:** Detect abstraction‑level mismatch and missing structural context.

**Mechanism:**
- Tree‑sitter parsing of code blocks
- Symbol resolution / call graph coverage
- File‑type expectations (README, design docs vs functions)

**Authority:**
- **Hard veto** when mandatory and failed

This signal explains most catastrophic failures observed historically.

---

### 5.5 Learned Advisor (Optional / Bounded)

**Purpose:** Improve recall on ambiguous cases

**Constraints:**
- Advisory only
- Cannot override structural or rule vetoes
- Output always logged separately

This component is removable without system collapse.

---

## 6. Decision Logic (Critical)

### 6.1 Veto Hierarchy

1. Structural insufficiency (if mandatory) → **Hard veto**
2. Rule/entity insufficiency → **Hard veto**
3. Semantic insufficiency → **Soft veto** (probable)
4. Learned advisor → **Never veto**

### 6.2 Final Verdicts

- `SUFFICIENT` – All mandatory axes passed
- `PROBABLY_SUFFICIENT` – No hard veto, some soft warnings
- `INSUFFICIENT` – Any hard veto triggered

No averaging. No voting.

---

## 7. Output Contract (Auditability)

Every run emits:

```json
{
  "final_verdict": "INSUFFICIENT",
  "deciding_factor": "STRUCTURAL",
  "signals": {
    "semantic": {"score": 0.91, "label": "SUFFICIENT"},
    "rule": {"score": 0.63, "label": "INSUFFICIENT"},
    "structural": {"score": 0.40, "label": "INSUFFICIENT"}
  }
}
```

This guarantees post‑mortem clarity.

---

## 8. Action Plan (How This Improves the System)

This layer enables **controlled recovery**, not silent failure.

When verdict ≠ SUFFICIENT:
- Block confident answering
- Trigger one of the following (policy‑driven, outside this layer):
  - Targeted re‑retrieval
  - Explicit user‑visible insufficiency explanation
  - Conservative answer mode

The sufficiency layer **never decides how to fix** — it only proves *what is missing*.

---

## 9. Why This Will Not Poison the System

- Read‑only
- Deterministic vetoes
- Explicit blame attribution
- No hidden mutation
- No learned authority

Failures become diagnosable instead of compounding.

---

## 10. Completion Status

**Problem 1 is now architecturally complete.**  
No further conceptual work is required before implementation.

Next problems (token governance, explanation depth, recovery strategies) are **downstream**, not blockers for this layer.

---

End of document.

