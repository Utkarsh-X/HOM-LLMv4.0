# V4 Query-Aware Target Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve deterministic target-file selection for omitted-target real-index tasks by using query/path lexical evidence in addition to retrieval scores.

**Architecture:** Keep the selector deterministic and conservative. File scores remain based on retrieval score, then receive a small additive boost for query tokens that match file path tokens. Ambiguity still applies when top scores are close and no lexical path signal separates them.

**Tech Stack:** Python, pytest, HOM-LLM v4 `EvidenceTargetFileSelector`.

---

### Task 1: Add Failing Selector Tests

**Files:**
- Modify: `tests/unit/v4/test_target_file_selector.py`

- [ ] **Step 1: Add path-token boost test**

Add:

```python
def test_target_selector_uses_query_path_tokens_to_break_close_scores() -> None:
    selector = EvidenceTargetFileSelector(min_score_margin=0.15)

    result = selector.select(
        TargetFileSelectionRequest(
            task_id="task-1",
            evidence_set=evidence_set(
                candidate("utils/string_tools.py", "cand-1", 0.60),
                candidate("utils/validators.py", "cand-2", 0.55),
            ),
        )
    )

    assert result.decision == "ambiguous"

    result = selector.select(
        TargetFileSelectionRequest(
            task_id="task-1",
            evidence_set=EvidenceSet(
                evidence_set_id="evidence-1",
                query="utils validators validate_email consecutive dots local part rejection",
                candidates=(
                    candidate("utils/string_tools.py", "cand-1", 0.60),
                    candidate("utils/validators.py", "cand-2", 0.55),
                ),
                diagnostics=evidence_set().diagnostics,
            ),
        )
    )

    assert result.decision == "selected"
    assert result.target_file == "utils/validators.py"
```

- [ ] **Step 2: Run selector tests to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_target_file_selector.py -q
```

Expected: FAIL because selector currently ignores query/path lexical evidence.

### Task 2: Implement Query/Path Boost

**Files:**
- Modify: `src/homllm_v4/planning/target_file_selector.py`

- [ ] **Step 1: Import regex**

Add:

```python
import re
```

- [ ] **Step 2: Add constructor parameter**

Change constructor:

```python
    def __init__(self, *, min_score_margin: float = 0.1, path_token_boost: float = 0.08) -> None:
        self.min_score_margin = max(0.0, float(min_score_margin))
        self.path_token_boost = max(0.0, float(path_token_boost))
```

- [ ] **Step 3: Add boost after retrieval-score aggregation**

Inside `select`, after score aggregation and before ranking:

```python
        query_tokens = _tokens(request.evidence_set.query)
        for file_path in tuple(scores):
            path_tokens = _tokens(file_path)
            scores[file_path] += self.path_token_boost * len(query_tokens & path_tokens)
```

- [ ] **Step 4: Add token helper**

Add:

```python
def _tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^A-Za-z0-9]+", value.lower()) if token}
```

- [ ] **Step 5: Run selector tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_target_file_selector.py -q
```

Expected: all selector tests pass.

### Task 3: Verify Real-Index Target-Selection Cases

**Files:**
- Continue modifications from `2026-05-16-v4-validator-target-selection-cases-plan.md`

- [ ] **Step 1: Run validator target-selection cases serially**

Run each new CLI case one at a time. Do not run them in parallel because the v3 DuckDB index can lock.

- [ ] **Step 2: Run full real-index benchmark**

Run full `eval-real-index-provider-patch` with fresh roots.

- [ ] **Step 3: Run full verification gates**

Run v4 tests, full unit tests, compileall, and forbidden v3 import scan.

- [ ] **Step 4: Update audits**

Record root cause and final evidence: target-omitted coverage now includes truncate, file path, and email semantic cases.
