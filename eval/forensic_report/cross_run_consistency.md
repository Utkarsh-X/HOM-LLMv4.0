# Cross-Run Consistency Findings

**Runs analyzed**: run_20260124_143034, run_20260125_091434, run_20260127_084123, run_20260129_134226.  
**Queries**: 3, 5, 8, 16, 18.

---

## 1. Did the same query vary meaningfully across runs?

| Query | Variance | Evidence |
|-------|----------|----------|
| **3** | Yes | Run 20260124: overall 1, “not in context.” Runs 20260125–20260129: overall 3–4, correct order + resolution; judge still prefers baseline for example/refs. |
| **5** | Yes | Run 20260124: overall 1, “get not present.” Later runs: improved, often candidate preferred. |
| **8** | No (stable) | All runs: improved or on par; candidate often preferred (concise, structured). |
| **16** | Yes (large) | Runs 20260124–20260127: improved or 5/4–5/3; correct batch-level, process method. Run 20260129: overall 2, “process missing,” item-level failure (wrong). |
| **18** | Yes (stable gap) | All runs with Q18: regressed; candidate “[not in context]” for 4/5 rules; no full example. |

**Conclusion**: Queries 3, 5, and 16 showed **meaningful cross-run variance** (same query correct in some runs, wrong or incomplete in others). Query 8 was **stable** (no gap). Query 18 was **stably weak** (context insufficient or over-trimmed every run).

---

## 2. Was the cause context shift or reasoning shift?

| Query | Primary cause | Evidence |
|-------|----------------|----------|
| **3** | **Context shift** | Run 20260124 lacked rule-order block; later runs had it. Same model; difference is which blocks were in prompt. |
| **5** | **Context shift** | Run 20260124 lacked `get`; later runs had it. |
| **8** | — | No meaningful variance. |
| **16** | **Context shift** | Run 20260129: model said “process not present” and inferred item-level; other runs had process and answered correctly. Telemetry (run_20260129): 23 blocks → 621 tokens after intelligence. So either retrieval/assembly did not include process block in that run, or intelligence phase removed it. |
| **18** | **Context shift** (and budget) | All runs: 13 blocks, 511 tokens after intelligence (run_20260129). Multi-file/multi-rule query gets fewer blocks and heavy trim; “4 of 5 rules not in context” is consistent with **insufficient or over-trimmed context** every run. |

**Conclusion**: Meaningful variance is **predominantly context shift** (which blocks retrieved and retained), not a pure “reasoning shift” with identical context. Reasoning **reacts** to context (surrender when thin; wrong inference in Q16 run_20260129).

---

## 3. Verdict and score stability (focus queries)

- **Q3**: Verdicts regressed → improved → improved → mixed; overall candidate 1 → 3 → 4 → 4 (with one regressed). **Unstable.**  
- **Q5**: Regressed → improved → improved → improved. **Stable after first run.**  
- **Q8**: Improved in all runs. **Stable.**  
- **Q16**: Improved → improved → improved → regressed. **Unstable** (one severe regression).  
- **Q18**: Regressed in all runs with Q18. **Stable** (consistently behind).

---

## 4. Confidence

- **Cross-run variance is real**: ≥ 0.8 (same query, different judge outcomes and correctness by run).  
- **Cause is primarily context shift**: ≥ 0.8 (supported by “[not in context],” “process not present,” telemetry block/token counts).  
- **Reasoning shift plays a role when context is thin**: 0.6–0.79 (wrong inference in Q16 run_20260129; surrender in Q18).

---

*End of Cross-Run Consistency.*
