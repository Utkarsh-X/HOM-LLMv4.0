# P1–P4 Diagnostic Telemetry: Flag and Save Path

## Flag to See and Save P1–P4 (Diagnostic Visibility)

You can run one or more of P1–P4 and **save their output to a separate file** using the runtime CLI flag:

- **`--diagnostic-layers`** — Comma-separated list of layers to run and save: `p1`, `p2`, `p3`, `p4`.

**Examples:**

```bash
# Save only P1 (sufficiency) and P2 (remediation) to a separate file
python runtime/run_query.py --query "How does X work?" --diagnostic-layers p1,p2

# Save all four layers
python runtime/run_query.py --query "Why does this fail?" --diagnostic-layers p1,p2,p3,p4 --json

# Save only P4 (explanation gap)
python runtime/run_query.py --query "Show me an example" --diagnostic-layers p4
```

**Where the file is saved:**

- Path: **`artifacts/runs/<run_id>/diagnostics.json`**
- `<run_id>` is the same run ID used for telemetry (e.g. `artifacts/runs/<uuid>/telemetry.json` when you use `--json`).
- The file is created as soon as the selected layers run (after context assembly and optional intelligence phase). You do **not** need `--json` for diagnostics to be written; `--diagnostic-layers` alone is enough.

**Contents of `diagnostics.json`:**

- A JSON object with keys `p1`, `p2`, `p3`, `p4` (only for layers you requested). Each value is the `to_dict()` output of that layer (final label, deciding trigger, per-signal breakdown, confidence, evidence volume, etc.).

**Notes:**

- P2 requires P1 (it consumes P1 output). If you pass `p2` without `p1`, P1 is still run so P2 can use it; only the layers you list are included in the saved JSON.
- P3 (instability) is run with the **current run only** (no history). So you get cold-start or single-run behaviour; for full history you would need to aggregate across runs elsewhere.
- All layers are **read-only**; they do not change query, context, retrieval, or generation.

---

## Previous State (for reference)

### Where is the telemetry path for P1–P4?

**Runtime path:** When you use **`--diagnostic-layers p1,p2,p3,p4`** (or any subset), the runtime (`runtime/run_query.py`) runs the selected layers after context assembly and writes their output to **`artifacts/runs/<run_id>/diagnostics.json`**. Without this flag, the four layers were not called from the main pipeline.

| Component | Calls P1–P4? | Saves / logs P1–P4? |
|-----------|----------------|----------------------|
| `homllm.generation.adapter` (GenerationAdapter) | **No** | **No** |
| `homllm.intelligence.controller` (DiagnosticController) | **No** (it runs L1/L2/L3 diagnostics only) | **No** |
| `eval/run_experiment.py`, `eval/run_judge.py` | **No** | **No** |
| Integration tests | **Yes** (for verification only) | **No** |

So today:

- **P1–P4 are never run** in the normal query → context → generation flow.
- **No code** writes `SufficiencyResult.to_dict()`, `RemediationResult.to_dict()`, `InstabilityResult.to_dict()`, or `ExplanationGapResult.to_dict()` to disk or to a logging backend.
- **There are no flags** to enable/disable or save P1–P4 diagnostics.

Each layer **does** expose machine-readable output for telemetry:

- **P1:** `SufficiencyResult.to_dict()` — `final_verdict`, `deciding_factor`, `intent`, `signals`
- **P2:** `RemediationResult.to_dict()` — `actions`, `trigger_to_actions`
- **P3:** `InstabilityResult.to_dict()` — `primary_label`, `confidence`, `evidence_volume`, `explanation`, `primary_deciding_signal`, `per_signal_scores`
- **P4:** `ExplanationGapResult.to_dict()` — `label`, `confidence`, `evidence_volume`, `rationale`, `deciding_trigger`, `per_signal_outputs`

But nothing in the repo currently calls these and persists the result.

---

## How to Add a Telemetry Path and Flags

If you want to **see** and **save** P1–P4 diagnostics:

### 1. Add a single “diagnostic telemetry” flag

Introduce one switch that controls whether P1–P4 are run and whether their output is saved (e.g. in run artifacts or a log).

**Possible places:**

- **Config:** e.g. in `homllm.common.config` or a small diagnostic config module:
  - `enable_diagnostic_telemetry: bool = False`  
  - Optional: `save_diagnostic_telemetry: bool = True` (when enabled, also write to disk).
- **CLI / env:** e.g. `--diagnostic-telemetry` or `HOMLLM_DIAGNOSTIC_TELEMETRY=1` for eval/experiment scripts.

No such flags exist today.

### 2. Add a telemetry path that runs P1–P4 and saves them

A minimal “telemetry path” would:

1. **Run** (in order):  
   P1 `run_sufficiency(query, context_artifact, embedder)` → P2 `run_remediation_from_sufficiency(p1, …)` → P3 `run_instability(runs, intent, …)` → P4 `run_explanation_gap(query, …)`.
2. **Collect** the four results and call `.to_dict()` on each.
3. **Save** only when the flag is on, e.g.:
   - **Eval runs:** next to `run_info.json` or `responses.jsonl`, e.g. `diagnostics_p1_p4.json` or one JSONL line per query.
   - **Generation path:** optional callback or side-car file (e.g. `diagnostics.json`) for the current query.

**Where to hook it:**

- **Eval:** In whatever script runs queries and writes `eval/runs/run_*/` (e.g. a runner that produces `responses.jsonl` and `run_info.json`). After each query (and after context assembly), call the four layers, build a dict (e.g. `p1`, `p2`, `p3`, `p4`), and if `save_diagnostic_telemetry` (or your flag) is True, write that dict (or append one JSONL line) to a file under that run directory.
- **Generation:** If you later wire diagnostics into the main app, the same “run P1–P4 → to_dict() → save if flag” logic can live in the generation adapter or a thin wrapper around it, again **without** changing retrieval, ranking, or prompts.

So:

- **Telemetry path:** “Where are P1–P4 run and their outputs saved?” → **Nowhere yet.** You add it by implementing the small runner above and calling it from eval (and optionally from generation) when the flag is on.
- **Flags to see/save:** **There are no flags today.** Adding one (e.g. `enable_diagnostic_telemetry` / `save_diagnostic_telemetry` or a CLI/env equivalent) and gating the new “run P1–P4 and save” code on it is the way to control whether they are run and saved.

---

## Summary

| Question | Answer |
|----------|--------|
| Where is the telemetry path for P1–P4? | **There isn’t one.** No code runs P1–P4 and saves their output. |
| Are there flags to see or save them? | **No.** No flags exist to enable/disable or save P1–P4 diagnostics. |
| How can we add seeing/saving? | Add a single flag (config or CLI/env) and a small path that runs P1–P4, calls `.to_dict()` on each result, and writes to a file (e.g. under `eval/runs/run_*/` or next to generation output) when the flag is on. |
