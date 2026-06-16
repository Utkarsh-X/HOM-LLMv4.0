# V4 Evidence Target Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic evidence-based target file selector so v4 can start moving from caller-supplied patch targets toward bounded autonomous target selection.

**Architecture:** Keep this as a pure planning utility first. It consumes an `EvidenceSet`, scores candidate files by retrieval score and candidate count, returns a selected target only when confidence is clear, and returns structured `ambiguous` or `no_candidates` decisions otherwise. It does not read files, call providers, apply patches, or mutate runtime state.

**Tech Stack:** Python dataclasses, pytest, HOM-LLM v4 evidence contracts.

---

### Task 1: Add Failing Selector Tests

**Files:**
- Create: `tests/unit/v4/test_target_file_selector.py`

- [ ] **Step 1: Write evidence helpers and three behavior tests**

Create the test file with:

```python
from homllm_v4.contracts.evidence import (
    EvidenceCandidate,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.planning.target_file_selector import (
    EvidenceTargetFileSelector,
    TargetFileSelectionRequest,
)


def candidate(file_path: str, candidate_id: str, score: float) -> EvidenceCandidate:
    return EvidenceCandidate(
        candidate_id=candidate_id,
        file_path=file_path,
        symbol_id=None,
        span_start=1,
        span_end=3,
        content_hash="hash",
        source_channels=("bm25",),
        bm25_score=score,
        vector_score=None,
        graph_score=None,
        retrieval_score=score,
        metadata={},
    )


def evidence_set(*candidates: EvidenceCandidate) -> EvidenceSet:
    return EvidenceSet(
        evidence_set_id="evidence-1",
        query="fix target",
        candidates=candidates,
        diagnostics=RetrievalDiagnostics(
            bm25_count=len(candidates),
            vector_count=0,
            graph_added_count=0,
            precision_added_count=0,
            coverage_added_count=0,
            retrieval_disagreement=None,
            degraded=False,
            degradation_reason=None,
        ),
    )


def test_target_selector_selects_clear_highest_scoring_file() -> None:
    selector = EvidenceTargetFileSelector()

    result = selector.select(
        TargetFileSelectionRequest(
            task_id="task-1",
            evidence_set=evidence_set(
                candidate("api/routes.py", "cand-1", 0.9),
                candidate("api/routes.py", "cand-2", 0.7),
                candidate("utils/helpers.py", "cand-3", 0.2),
            ),
        )
    )

    assert result.decision == "selected"
    assert result.target_file == "api/routes.py"
    assert result.confidence > 0.0
    assert result.candidate_file_scores["api/routes.py"] > result.candidate_file_scores["utils/helpers.py"]


def test_target_selector_returns_ambiguous_for_close_file_scores() -> None:
    selector = EvidenceTargetFileSelector(min_score_margin=0.15)

    result = selector.select(
        TargetFileSelectionRequest(
            task_id="task-1",
            evidence_set=evidence_set(
                candidate("api/routes.py", "cand-1", 0.6),
                candidate("utils/helpers.py", "cand-2", 0.55),
            ),
        )
    )

    assert result.decision == "ambiguous"
    assert result.target_file is None
    assert result.reason == "top_file_scores_too_close"


def test_target_selector_returns_no_candidates_for_empty_evidence() -> None:
    selector = EvidenceTargetFileSelector()

    result = selector.select(
        TargetFileSelectionRequest(
            task_id="task-1",
            evidence_set=evidence_set(),
        )
    )

    assert result.decision == "no_candidates"
    assert result.target_file is None
    assert result.reason == "evidence_set_has_no_candidates"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_target_file_selector.py -q
```

Expected: FAIL because `homllm_v4.planning.target_file_selector` does not exist.

### Task 2: Implement Pure Target Selector

**Files:**
- Create: `src/homllm_v4/planning/target_file_selector.py`

- [ ] **Step 1: Add request/result dataclasses**

Implement:

```python
from dataclasses import dataclass
from typing import Literal

from homllm_v4.contracts.evidence import EvidenceSet

TargetSelectionDecision = Literal["selected", "ambiguous", "no_candidates"]


@dataclass(frozen=True)
class TargetFileSelectionRequest:
    task_id: str
    evidence_set: EvidenceSet


@dataclass(frozen=True)
class TargetFileSelectionResult:
    decision: TargetSelectionDecision
    target_file: str | None
    confidence: float
    reason: str | None
    candidate_file_scores: dict[str, float]
```

- [ ] **Step 2: Add deterministic selector**

Implement:

```python
class EvidenceTargetFileSelector:
    def __init__(self, *, min_score_margin: float = 0.1) -> None:
        self.min_score_margin = max(0.0, float(min_score_margin))

    def select(self, request: TargetFileSelectionRequest) -> TargetFileSelectionResult:
        scores: dict[str, float] = {}
        for candidate in request.evidence_set.candidates:
            scores[candidate.file_path] = scores.get(candidate.file_path, 0.0) + float(
                candidate.retrieval_score or 0.0
            )

        if not scores:
            return TargetFileSelectionResult(
                decision="no_candidates",
                target_file=None,
                confidence=0.0,
                reason="evidence_set_has_no_candidates",
                candidate_file_scores={},
            )

        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        top_file, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = top_score - second_score
        total = sum(scores.values())
        confidence = top_score / total if total > 0 else 0.0

        if len(ranked) > 1 and margin < self.min_score_margin:
            return TargetFileSelectionResult(
                decision="ambiguous",
                target_file=None,
                confidence=confidence,
                reason="top_file_scores_too_close",
                candidate_file_scores=dict(ranked),
            )

        return TargetFileSelectionResult(
            decision="selected",
            target_file=top_file,
            confidence=confidence,
            reason=None,
            candidate_file_scores=dict(ranked),
        )
```

- [ ] **Step 3: Run selector tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_target_file_selector.py -q
```

Expected: `3 passed`.

### Task 3: Verify and Audit

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`

- [ ] **Step 1: Run v4 tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
```

Expected: all v4 tests pass.

- [ ] **Step 2: Run full unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
```

Expected: all unit tests pass.

- [ ] **Step 3: Run compile and boundary gates**

Run compileall and forbidden v3 import scan.

- [ ] **Step 4: Update audits honestly**

Record that a pure deterministic target-selection foundation exists. Keep the remaining gap explicit: provider-proposed write planning still requires caller-supplied `target_file` until selector wiring is added.
