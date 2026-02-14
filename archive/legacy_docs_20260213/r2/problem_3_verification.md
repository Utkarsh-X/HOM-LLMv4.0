# Problem 3 — Cross-Run Instability Detection: Verification Note

## Status
Implementation is complete and unit-tested. All mandatory constraints and checklist items are satisfied. This layer is **diagnostic only**; no action or remediation logic.

---

## 1. Output Contract ✓

| Spec requirement | Implementation |
|------------------|----------------|
| Exactly one primary label: STABLE \| UNSTABLE_CONTEXT \| UNSTABLE_REASONING | `InstabilityResult.primary_label` is a single `PrimaryLabelType`; pipeline never emits a fourth or mixed label. |
| confidence | `InstabilityResult.confidence` (correctness likelihood; cold-start = 0.5). |
| evidence_volume | `InstabilityResult.evidence_volume` (number of historical runs in bucket). |
| explanation | `InstabilityResult.explanation` (per-signal scores dict). |
| primary_deciding_signal | `InstabilityResult.primary_deciding_signal` (name of winning signal). |
| secondary_contributors (optional) | `InstabilityResult.secondary_contributors` (signals above mild threshold, excluding primary). |

---

## 2. Historical Bucketing ✓

- **Intent class** + **coarse embedding similarity** (cosine ≥ 0.85): `bucket_runs()` in `src/homllm/instability/bucketing.py`.
- Same intent required; if `reference_embedding` and run `query_embedding` are present, run included only when `cosine(run.query_embedding, reference_embedding) ≥ BUCKET_EMBEDDING_SIMILARITY_THRESHOLD`.
- Prefer over-separation: strict threshold; no inference when embeddings absent (intent-only filter).

---

## 3. Signals (All Implemented) ✓

| Signal | Module | Output |
|--------|--------|--------|
| Retrieval overlap statistics | `signals/retrieval_overlap.py` | Jaccard on chunk IDs; low overlap → high instability → UNSTABLE_CONTEXT. |
| Context metadata variance | `signals/metadata_variance.py` | Variance in file count and unique-extension count; high → UNSTABLE_CONTEXT. |
| Historical failure frequency | `signals/failure_frequency.py` | Raw runs only (anti-amplification); fraction non-SUFFICIENT → UNSTABLE_CONTEXT. |
| Embedding consistency | `signals/embedding_consistency.py` | Variance of context centroid across runs; high → UNSTABLE_CONTEXT (Stage 2). |
| Answer-structure variance | `signals/answer_structure.py` | Token count, section count, code block, list density, refusal markers; high → UNSTABLE_REASONING. |

---

## 4. Evaluation Flow ✓

| Stage | Behavior |
|-------|----------|
| **Stage 0** | Cold-start guard: `evidence_volume < COLD_START_MIN_RUNS` (5) → UNSTABLE_CONTEXT, confidence 0.5, `cold_start=True`, explicit note. |
| **Stage 1** | Mandatory veto: retrieval_overlap, metadata_variance, failure_frequency, answer_structure_variance computed in parallel; **highest instability score wins immediately** (no averaging). |
| **Stage 2** | Refinement: only if no clear veto (max Stage 1 score < VETO_THRESHOLD). Embedding consistency used to disambiguate; if emb_score ≥ VETO_THRESHOLD → UNSTABLE_CONTEXT, else → STABLE. |

---

## 5. Label Semantics ✓

- **Context drift** (retrieval overlap, metadata variance, failure frequency, embedding consistency) → UNSTABLE_CONTEXT.
- **Stable context + oscillating answer structure** (answer_structure_variance) → UNSTABLE_REASONING.
- No fourth label; no mixed primary; secondary_contributors are explanatory only.

---

## 6. Anti-Amplification Rule ✓

- **Raw vs policy-influenced**: `failure_frequency()` uses only runs with `policy_influenced=False`. Policy-influenced runs are excluded from failure counts.
- Only raw counters influence labels; `RunRecord.policy_influenced` is respected in `failure_frequency`.

---

## 7. Auditability ✓

- **Per-signal scores**: `InstabilityResult.per_signal_scores` (SignalScore: signal_name, score, label, threshold_triggered).
- **Thresholds triggered**: `InstabilityResult.thresholds_triggered`.
- **Deciding signal**: `InstabilityResult.primary_deciding_signal`.
- **Evidence volume**: `InstabilityResult.evidence_volume`.
- **Blame attribution**: `to_dict()` emits all of the above; machine-readable for logging and post-mortem.

---

## 8. Mandatory Constraints ✓

| Constraint | Status |
|------------|--------|
| Read-only: no mutation of retrieval, ranking, generation, prompts | No code mutates context, retrieval, ranking, or prompts. |
| No LLM calls; frozen embeddings and deterministic statistics only | All signals use Jaccard, variance, counts, and optional precomputed embeddings; no generation or judging. |
| No averaging or voting; strongest instability signal wins | Stage 1: `max(scores, key=score)`; single winner. |
| Conservative bias: uncertainty → instability | Cold-start → UNSTABLE_CONTEXT; low evidence treated as unstable. |
| Reversible: removable with zero side effects | Layer is additive; removing it leaves system behavior unchanged. |

---

## 9. Package Layout

- **`src/homllm/instability/`**
  - `interfaces.py` — RunRecord, InstabilityResult, SignalScore, PrimaryLabelType, VerdictType
  - `constants.py` — COLD_START_MIN_RUNS, BUCKET_EMBEDDING_SIMILARITY_THRESHOLD, VETO_THRESHOLD, REFUSAL_MARKERS, etc.
  - `utils.py` — cosine_similarity, jaccard_similarity, variance, normalized_variance
  - `bucketing.py` — bucket_runs(intent, reference_embedding)
  - `signals/` — retrieval_overlap, metadata_variance, failure_frequency, embedding_consistency, answer_structure
  - `pipeline.py` — run_instability(runs, intent, reference_embedding)

---

## 10. Tests

- **`tests/unit/test_instability_layer.py`** — 13 tests:
  - Cold-start: UNSTABLE_CONTEXT, medium confidence, cold_start=True
  - Context drift: low retrieval overlap → UNSTABLE_CONTEXT; metadata variance
  - Reasoning instability: answer-structure variance
  - Failure frequency: raw-only; all policy_influenced → 0
  - Bucketing: intent filter; embedding proximity
  - Output contract: exactly one primary label
  - Auditability: per_signal_scores, primary_deciding_signal, to_dict()
  - Secondary contributors

Run: `PYTHONPATH=src python -m pytest tests/unit/test_instability_layer.py -v`

---

## 11. Verification Requirements

- **Previously observed brittle queries**: The layer would flag them when (1) retrieval overlap is low across runs, (2) metadata or failure frequency is high, or (3) answer structure oscillates with stable context. Cold-start would also flag queries with fewer than 5 historical runs.
- **No new coupling or hidden intelligence**: No LLM calls; no feedback loops; no adaptive learning. Inputs are historical RunRecords and optional reference embedding; output is a single InstabilityResult.
- **Removing the layer**: Leaves retrieval, ranking, generation, and prompts unchanged; no side effects.

---

## 12. Out of Scope (As Specified)

- No action logic or remediation; diagnostic only.
- No learning loops or runtime mutation of thresholds.
