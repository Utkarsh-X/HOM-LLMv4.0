# Problem 4 — Structural Explanation Gap Detection: Verification Note

## Status
Implementation is complete and unit-tested. All hard constraints and verification checklist items are satisfied. This layer is **diagnostic only**; advisory guidance only; no generation, retrieval, or prompt mutation.

---

## 1. Output Contract ✓

| Spec requirement | Implementation |
|------------------|----------------|
| Exactly one label: SHALLOW_OK \| DETAILED_REQUIRED \| EXAMPLE_RECOMMENDED | `ExplanationGapResult.label` is a single `DepthLabelType`. |
| Confidence (bounded) | `ExplanationGapResult.confidence`; cold-start = 0.5; no inflation from single signal. |
| Evidence volume | `ExplanationGapResult.evidence_volume` (history count). |
| Rationale | `ExplanationGapResult.rationale` (machine-readable). |
| Deciding trigger | `ExplanationGapResult.deciding_trigger` (Rule / History / Embedding / Classifier). |
| Per-signal outputs | `ExplanationGapResult.per_signal_outputs` (SignalOutput: signal_name, label, trigger, score_or_note). |

---

## 2. Hard Constraints ✓

| Constraint | Status |
|------------|--------|
| No LLM calls | All logic is rule-based, embedding (frozen), or stub classifier (no-op). |
| No generation, rewriting, verbosity injection | Layer only emits a label and metadata; no content generation. |
| No retrieval, ranking, or prompt mutation | Read-only; no mutation of retrieval, ranking, or prompts. |
| No probabilistic voting or averaging | Stage 1: most severe trigger dominates; Stage 2/3: upgrade only. |
| Deterministic rules, frozen embeddings | Rules are regex; embeddings optional and precomputed or from frozen embedder. |
| Conservative bias: over-explain safely | Escalation only upward; ambiguity never yields SHALLOW_OK when rules fire; cold-start preserved. |

---

## 3. Required Architecture ✓

### Stage 1 — Mandatory Escalation (Always Run)
- **Rule-based pattern matching**: `rules.py` — keywords (why, how, explain, example, show, error, execution path, etc.); question form; debugging markers. Most severe trigger dominates (EXAMPLE_RECOMMENDED > DETAILED_REQUIRED > SHALLOW_OK).
- **Historical depth recurrence**: `history.py` — read-only stats per bucket (`HistoryDepthStats`: runs_in_bucket, pct_expanded_or_manual, pct_shallow_complaints). Cold-start when no history; escalation when pct ≥ threshold. Only escalates; never downgrades.
- No downgrades after escalation; severity order enforced via `max_severity()`.

### Stage 2 — Semantic Refinement
- **Only if Stage 1 is SHALLOW_OK**: `embedding_refinement.py` — optional query embedding and intent centroids (illustrative, explanatory, factual). Upgrades to DETAILED_REQUIRED or EXAMPLE_RECOMMENDED when similarity to explanatory/illustrative centroid ≥ threshold. Never downgrades.

### Stage 3 — Precision Upgrade (Optional, Contained)
- **Classifier stub**: `classifier_stub.py` — no-op; returns current label. Future: offline classifier may only upgrade; never downgrade; ambiguity never yields SHALLOW_OK.

---

## 4. Intent-to-Depth Invariants ✓

| Intent Class | Default | Mandatory Escalation Triggers |
|--------------|---------|-------------------------------|
| Factual / What-Is | SHALLOW_OK | None |
| Explanatory / Why-How | DETAILED_REQUIRED | why / how / causal verbs |
| Debugging / Behavior | DETAILED_REQUIRED | errors, execution paths |
| Illustrative | EXAMPLE_RECOMMENDED | show / example / sample |

- Encoded in `constants.py`: `INTENT_DEFAULT`, `RULE_PATTERNS` (PATTERNS_EXAMPLE, PATTERNS_DETAILED, PATTERNS_DEBUG).
- Version: `INTENT_TABLE_VERSION = "1.0"`.
- Intent classification: `classify_depth_intent()` in `rules.py`; default applied when no rule fires.

---

## 5. Confidence & Evidence Semantics ✓

- **Confidence** = likelihood recommendation is correct; cold-start = 0.5; bounded (no inflation from single signal).
- **Evidence volume** = number of historical runs in bucket (from `HistoryDepthStats` or 0).
- Cold-start when evidence_volume < 2 → medium confidence + low evidence; `cold_start=True` in result.

---

## 6. Auditability ✓

Each output includes:
- Final label
- Deciding trigger (Rule / IntentDefault / History / Embedding / Classifier)
- Per-signal outputs (rule_patterns, historical_depth, embedding_refinement, classifier_stage3)
- Confidence
- Evidence volume
- `to_dict()` for machine-readable logging

---

## 7. Verification Checklist ✓

| Item | Status |
|------|--------|
| Escalation only upward (never downgrade) | `max_severity()` used throughout; history and embedding only upgrade; classifier stub no-op. |
| Rules dominate classifiers | Stage 1 runs first; Stage 2 only when Stage 1 is SHALLOW_OK; Stage 3 stub never overrides rule trigger. |
| Ambiguity never yields SHALLOW_OK | When rules fire (example/detailed/debug), label is escalated; intent default for FACTUAL is SHALLOW_OK only when no rule matches. |
| No mutation of prompts, retrieval, or generation | No code mutates prompts, retrieval, or generation. |
| Layer removable with zero side effects | Package is additive; removing it leaves rest of system unchanged. |
| Deterministic outputs for identical inputs | Same query + same optional args → same label and deciding_trigger (tests assert this). |

---

## 8. Package Layout

- **`src/homllm/explanation_gap/`**
  - `interfaces.py` — DepthLabelType, DepthIntentType, ExplanationGapResult, SignalOutput, HistoryDepthStats, max_severity, severity_rank
  - `constants.py` — INTENT_TABLE_VERSION, INTENT_DEFAULT, RULE_PATTERNS, COLD_START_CONFIDENCE, HISTORY_ESCALATION_PCT, EMBEDDING_UPGRADE_THRESHOLD, SEED_*
  - `rules.py` — classify_depth_intent, rule_based_depth
  - `history.py` — historical_depth_escalation
  - `embedding_refinement.py` — embedding_refinement (Stage 2)
  - `classifier_stub.py` — classifier_upgrade_only (Stage 3)
  - `pipeline.py` — run_explanation_gap, run_explanation_gap_with_embedder

---

## 9. Tests

- **`tests/unit/test_explanation_gap_layer.py`** — 20 tests:
  - Severity order and max_severity (no downgrade)
  - Intent table versioned and defaults
  - Rule-based: example / detailed / debug / factual
  - classify_depth_intent
  - Historical: cold-start, escalation when high pct, never downgrade
  - Pipeline: exactly one label, auditability, to_dict, cold-start
  - Example beats detailed; ambiguity never shallow when rules fire; deterministic

Run: `PYTHONPATH=src python -m pytest tests/unit/test_explanation_gap_layer.py -v`

---

## 10. Usage

```python
from homllm.explanation_gap import run_explanation_gap, run_explanation_gap_with_embedder

# Without embedder (Stage 2 silent)
out = run_explanation_gap("Why does this fail?", history_stats=None)
# out.label, out.deciding_trigger, out.confidence, out.evidence_volume

# With embedder (Stage 2 may upgrade)
out = run_explanation_gap_with_embedder("Explain how it works", embedder=embedder)
```

The layer **emits advisory guidance only**; it does not inject content, modify prompts, or change retrieval/generation.
