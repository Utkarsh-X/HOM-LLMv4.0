# Problem 3: Cross-Run Instability Detection

## Purpose
Detect longitudinal brittleness across multiple executions of the *same or semantically equivalent query* without mutating retrieval, ranking, or generation. This layer is **purely diagnostic, read-only, and advisory**.

It answers a different question than Problems 1 and 2:
> *Is this query-answering behavior trustworthy over time?*

---

## Output Contract

**Primary Label (exactly one):**
- `STABLE`
- `UNSTABLE_CONTEXT`
- `UNSTABLE_REASONING`

**Accompanying Fields:**
- `confidence` – likelihood that the instability classification is correct (not evidence volume).
- `evidence_volume` – number of historical runs used.
- `explanation` – per-signal breakdown.
- `primary_deciding_signal`
- `secondary_contributors` (optional)

No mutation, retries, or ranking changes are permitted.

---

## Intelligence Constraints (Invariants)

- **Read-only only** – consumes historical logs and metadata.
- **No LLM calls** – embeddings allowed; no generation or judging.
- **No averaging** – strongest instability signal dominates.
- **Conservative bias** – uncertainty defaults toward instability.
- **Reversible** – removable without side effects.

---

## Inputs

- Query text
- Query intent classification (shared with Problems 1/2)
- Retrieval metadata per run (chunk IDs, file paths, tags)
- Context summary stats (from Problems 1/2)
- Historical run logs (answers, verdicts, metadata)

---

## Query Bucketing (Historical Scope)

Runs are grouped before analysis using:
1. **Intent Class** (architectural, behavioral, implementation, etc.)
2. **Coarse Embedding Proximity** (frozen encoder; cosine ≥ 0.85)

Design rule: *Prefer over-separation to false evidence propagation.*

---

## Signal Classes (All Read-Only)

### 1. Retrieval Overlap Statistics
- Jaccard / set similarity on chunk IDs or metadata hashes.
- Low overlap → `UNSTABLE_CONTEXT`.

### 2. Context Metadata Variance
- Variance in file-type distribution, level tags, diversity metrics.
- High variance → `UNSTABLE_CONTEXT`.

### 3. Historical Failure Pattern Frequency
- Frequency of Problem 1/2 downgrades per bucket.
- Recurring misalignment → instability classification.

### 4. Embedding Consistency
- Variance of frozen centroid embeddings across runs.
- Semantic drift → context instability proxy.

### 5. Answer-Structure Variance (Added Signal)
Purely structural analysis of historical answers:
- Token count variance
- Section/header count
- Code block presence
- List density
- Refusal/surrender marker frequency
- Reference/citation density

Rule:
> Stable context + high structure variance → `UNSTABLE_REASONING`

---

## Staged Evaluation Logic

### Stage 0: Cold-Start Guard
If `evidence_volume < N` (e.g., 5 runs):
- Emit `UNSTABLE_CONTEXT`
- Medium confidence
- Explicit cold-start note

### Stage 1: Mandatory Historical Veto (Always Run)
Parallel evaluation:
- Retrieval overlap
- Metadata variance
- Failure frequency
- Answer-structure variance

Highest instability score **wins immediately**.

### Stage 2: Refinement (If No Clear Veto)
- Embedding consistency used to disambiguate subtle drift.

---

## Label Selection Rules

- **Primary label** = signal with strongest instability evidence.
- **Secondary contributors** recorded if above mild threshold.
- No fourth label permitted.

Examples:
- Retrieval overlap low → `UNSTABLE_CONTEXT`
- Stable context + oscillating depth → `UNSTABLE_REASONING`

---

## Confidence Semantics

- `confidence` = correctness likelihood (signal clarity).
- `evidence_volume` reported separately.

Cold-start confidence is intentionally conservative.

---

## Anti-Amplification Safeguard

To prevent policy-induced instability loops:
- Maintain **two counters** per bucket:
  - Raw instability
  - Policy-influenced runs

Only raw counters influence labels.

---

## Auditability

Every run emits:
- Per-signal scores
- Thresholds triggered
- Deciding signal
- Evidence volume

Blame attribution is explicit and machine-readable.

---

## Failure Modes Explicitly Covered

- Retrieval drift
- Context composition variance
- Semantic drift
- Reasoning depth oscillation
- Repeated surrender patterns
- Mixed instability (via secondary contributors)

---

## Freeze Conditions

This design is frozen upon documentation of:
- Structural feature thresholds
- Bucket invariants
- Cold-start constants

No learning loops, no runtime mutation.

---

## Design Philosophy (Summary)

This layer does not *fix* instability.
It **exposes brittleness early and honestly**, enabling informed downstream decisions without compromising system integrity.

It completes the diagnostic foundation required before any agentic or adaptive behaviors are considered.

