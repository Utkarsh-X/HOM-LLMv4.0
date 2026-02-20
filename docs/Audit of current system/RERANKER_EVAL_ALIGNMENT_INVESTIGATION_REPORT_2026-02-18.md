# RERANKER vs EVALUATION ALIGNMENT INVESTIGATION REPORT

- Generated (UTC): `2026-02-19T05:01:54.106664+00:00`
- Labels source: `eval\runs\stage2_geometry_lock_only_flags_repro\candidate_signal_alignment_labels.jsonl`
- Config: `configs\validation_qexp_off.yaml`

## Highlighted Root-Cause Section
- **ROOT_CAUSE = RERANKER_SIGNAL_WEAK**
- **CONFIDENCE_LEVEL = medium**

## Phase-2 Correlation Summary
- base_vs_judged (Pearson mean): `0.4691708201290768`
- rerank_raw_vs_judged (Pearson mean): `-0.17743144080442375`
- rerank_scaled_vs_judged (Pearson mean): `-0.15597297191027595`
- lexical_overlap_vs_judged (Pearson mean): `0.6295060566073529`
- chunk_length_vs_judged (Pearson mean): `0.5424486175577903`

## Phase-3 Formatting Sensitivity (Top-50)
- format A/B Spearman mean: `0.8229775812365867`
- format A/B Spearman p25: `0.8033462033462033`
- format A/B Spearman p75: `0.8505226480836235`
- mean truncation rate top50: `0.10932417420142067`

## Phase-5 No-Normalization Control
- mean tau raw_vs_judged: `-0.10804084199661403`
- mean tau scaled_vs_judged: `-0.09761056413743602`
- mean tau(raw-scaled): `-0.010430277859178024`

## Decision Matrix
| Hypothesis | Supported | Evidence Strength | Notes |
|---|---|---|---|
| Reranker signal weak | True | high | Base-vs-rerank judged correlation and tau. |
| Judge misaligned | False | low | Phase-1 human-style proxy agreement counts. |
| Scaling distortion | False | low | Raw-logit tau vs scaled-logit tau. |
| Formatting issue | True | medium | A/B formatting correlation on top-50 candidates. |
| Chunking bias | True | medium | Length/lexical bias differential. |
| Domain mismatch | False | low | Weak signal with no strong scaling/formatting failure. |

## Final Decision Gate
- At least one controlled input/format/scaling change materially improves tau: `False`

- Machine-readable JSON: `eval\runs\reranker_eval_alignment_investigation\20260219_041443\alignment_investigation.json`
