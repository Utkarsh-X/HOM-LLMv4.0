# Problem 2 — Action & Remediation Layer: Implementation Verification

## Status
Implementation is complete and unit-tested. This document maps the spec to the codebase.

---

## 1. Contract Compliance

| Spec § | Requirement | Implementation |
|--------|-------------|----------------|
| §3 | Consume P1 fields: final_label, deciding_factor, intent_class, failed_axes[], negative_evidence[], confidence, fragility_flag | `RemediationInput` in `src/homllm/remediation/interfaces.py`. Adapter derives `final_label` and `failed_axes` from `SufficiencyResult`; optional fields default to empty/None. No inference of missing data. |
| §3 | If field absent → no action | Pipeline only adds actions for axes in `failed_axes` that have a matrix mapping; unknown axes yield no action. |
| §5 | Action classes: Retrieval-Level, Token Budget, Prompt Strategy, Retry/Escalation | `ActionType` literal and matrix in `matrix.py`: RETRIEVAL_EXPANSION, RETRIEVAL_RE_TARGET, TOKEN_BUDGET_INCREASE, PROMPT_STRATEGY, RETRY_ESCALATION. |
| §6 | Deterministic mapping: Structural Absence → Retrieval Expansion; Fragmentation → Token Budget; Wrong Subsystem → Re-target; Explanation Gap → Prompt Strategy; Historical Fragility → Retry/Escalation | `_DECIDING_FACTOR_TO_ACTION`: STRUCTURAL→RETRIEVAL_EXPANSION, RULE→RETRIEVAL_RE_TARGET, SEMANTIC→TOKEN_BUDGET_INCREASE. `action_for_fragility()` for RETRY_ESCALATION. |
| §7 | Ordering: Structural first, Token second, Prompt last; one action per axis per run | `sort_actions_by_priority()` and pipeline deduplication by axis; at most one action per failed axis. |
| §8 | Each action: action_type, trigger_signal, expected_effect, actual_outcome (post‑hoc) | `RemediationAction` dataclass and `RemediationResult.to_dict()` for logging. |

---

## 2. Package Layout

- **`src/homllm/remediation/`**
  - `interfaces.py` — RemediationInput, RemediationAction, RemediationResult, types
  - `adapter.py` — `sufficiency_to_remediation_input(SufficiencyResult, fragility_flag=...)`
  - `matrix.py` — `allowed_action_for_deciding_factor()`, `action_for_fragility()`, `sort_actions_by_priority()`
  - `pipeline.py` — `run_remediation(RemediationInput)`, `run_remediation_from_sufficiency(SufficiencyResult, fragility_flag=...)`

---

## 3. P1 → P2 Mapping

- **Verdict → Label**: SUFFICIENT→ALIGNED, PROBABLY_SUFFICIENT→PARTIALLY_ALIGNED, INSUFFICIENT→MISALIGNED
- **failed_axes**: Derived from P1 `signals` where `label == "INSUFFICIENT"` (semantic→SEMANTIC, rule→RULE, structural→STRUCTURAL)
- **fragility_flag**: Not emitted by P1; optional argument when calling the adapter/pipeline (e.g. from run history)

---

## 4. Non‑Goals Respected

- Does not re-classify intent, re-interpret sufficiency, or override vetoes
- Does not mutate Problem‑1; consumes its output only
- No generative intelligence; selection is procedural and bounded
- Removing Problem‑2 leaves Problem‑1 intact

---

## 5. Tests

- **`tests/unit/test_remediation_layer.py`** — 19 tests covering adapter, matrix, ordering, pipeline (ALIGNED→no action, one per axis, fragility), observability contract, and unknown-axis→no action.

Run: `PYTHONPATH=src python -m pytest tests/unit/test_remediation_layer.py -v`

---

## 6. Usage

```python
from homllm.sufficiency import run_sufficiency
from homllm.remediation import run_remediation_from_sufficiency

# After P1 diagnostic
sufficiency_result = run_sufficiency(query, context_artifact, embedder)
remediation_result = run_remediation_from_sufficiency(
    sufficiency_result,
    fragility_flag=False,  # set True if run history shows repeated MISALIGNED
)
for action in remediation_result.actions:
    # action.action_type, action.trigger_signal, action.expected_effect
    # actual_outcome filled post‑hoc by caller
    ...
```

The layer **emits** actions only; it does not execute retrieval, token budget, or prompt changes. The caller is responsible for applying actions and recording `actual_outcome`.
