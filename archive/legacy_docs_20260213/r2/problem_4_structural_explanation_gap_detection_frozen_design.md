# Problem 4: Structural Explanation Gap Detection

## Status
**Frozen — Design Complete**

This document specifies the final, bounded, read-only diagnostic design for **Structural Explanation Gap Detection** in the HLLM system. It is consistent with the frozen designs of Problems 1–3 and introduces no mutation, generation, or hidden intelligence.

---

## 1. Problem Definition

### Objective
Detect whether a query **inherently requires explanatory depth beyond a shallow factual answer**, without generating explanations or modifying responses.

### Core Question
> *Does this query require “why”, stepwise reasoning, synthesis, or examples to be considered complete by a reasonable expert?*

### Outputs (Advisory Only)
- **SHALLOW_OK** — Brief factual response sufficient.
- **DETAILED_REQUIRED** — Stepwise explanation, synthesis, or reasoning expected.
- **EXAMPLE_RECOMMENDED** — Illustrations, code samples, or concrete examples critical.

Each output includes:
- Confidence (bounded)
- Machine-readable rationale
- Deciding trigger(s)

---

## 2. Hard Constraints (Invariants)

The system **MUST NOT**:
- Generate explanations
- Inject content or verbosity
- Modify retrieval or generation
- Enforce formatting

The system **MAY**:
- Analyze query text
- Use rules, embeddings, lightweight classifiers
- Use historical (read-only) statistics
- Emit advisory guidance only

Bias preference:
> **Over-explain safely rather than under-explain**

---

## 3. Failure Modes Covered

| Failure Mode | Description |
|-------------|------------|
| Missing “Why” | Correct facts but no reasoning/synthesis |
| Structural Shallow | Answer lacks steps, ordering, causality |
| Example Absence | Abstract explanation where concrete illustration is expected |
| Implicit Depth | Query implies depth without explicit keywords |
| Recurrent Shallow | Historically shallow on similar queries |

---

## 4. Detection Approaches (Non-LLM)

### 4.1 Rule-Based Pattern Matching (Mandatory)

Deterministic triggers using:
- Keywords: `why`, `explain`, `how does`, `step by`, `reason`, `example`, `show`
- Question form: explanatory WH-phrases
- Debug/behavioral markers: `error`, `happens when`, `edge case`

**Properties**:
- Zero latency risk
- Fully auditable
- No drift

---

### 4.2 Embedding-Based Intent Clustering

- Frozen encoder (Sentence-BERT / E5)
- Distance to pre-labeled intent centroids:
  - Factual
  - Explanatory
  - Illustrative

Used only when rules do not trigger.

---

### 4.3 Lightweight Depth Classifier (Contained)

- Offline-trained small model (e.g., DeBERTa-small)
- Inputs: query text + pattern flags + embedding features
- Output: trichotomy + confidence

**Containment Rules**:
- Cannot downgrade from rule-triggered escalation
- Cannot emit SHALLOW_OK if ambiguity exists

---

### 4.4 Historical Depth Pattern Frequency

Read-only statistics per query bucket:
- % prior runs expanded manually
- % prior shallow complaints or failures

Cold-start behavior:
- No history → conservative escalation

---

## 5. Hybrid Decision Architecture

### Stage 1 — Mandatory Escalation (Always Run)

Parallel:
- Rule-based patterns
- Historical depth recurrence

**Rule**: Most severe trigger dominates

```
EXAMPLE_RECOMMENDED > DETAILED_REQUIRED > SHALLOW_OK
```

No early downgrade allowed.

---

### Stage 2 — Semantic Refinement

Embedding clustering detects implicit depth intent when Stage 1 is silent.

---

### Stage 3 — Precision Upgrade (Optional)

Classifier may **only upgrade** recommendation.

---

## 6. Intent-to-Depth Invariant Table

| Query Intent Class | Default | Mandatory Escalation Triggers | Historical Sensitivity |
|------------------|---------|-------------------------------|------------------------|
| Factual / What-Is | SHALLOW_OK | None | Low |
| Explanatory / Why-How | DETAILED_REQUIRED | `why`, `how`, causal verbs | High |
| Debugging / Behavior | DETAILED_REQUIRED | Errors, execution paths | Medium |
| Illustrative | EXAMPLE_RECOMMENDED | `show`, `example`, `sample` | High |

This table is **authoritative** and must be versioned.

---

## 7. Confidence Semantics

- Confidence = likelihood recommendation is correct
- Separate `evidence_volume` field (history count)
- Cold-start: medium confidence + low evidence

No confidence inflation allowed.

---

## 8. Auditability Requirements

Each run emits:
- Final label
- Per-signal outputs
- Deciding trigger
- Historical evidence count

Example:
```
Label: DETAILED_REQUIRED
Deciding Trigger: Rule("why")
Supporting Signals: Embedding intent proximity
Confidence: 0.86
Evidence Volume: 14
```

---

## 9. Fail-Safe Behavior

- Ambiguity → escalate, never suppress
- Removal of any component degrades conservatively
- No learning online
- Fully reversible

---

## 10. Freeze Criteria

This design is frozen when:
- Intent table is finalized
- Rule sets are versioned
- Thresholds documented

No further intelligence expansion permitted without reopening the problem.

---

## 11. Role in the HLLM System

Problem 4 provides **explanation-depth guidance** only.
It complements:
- Problem 1 (Context Sufficiency)
- Problem 2 (Context Alignment)
- Problem 3 (Cross-Run Stability)

Together, they form a complete **diagnostic foundation** for trustworthy generation.

