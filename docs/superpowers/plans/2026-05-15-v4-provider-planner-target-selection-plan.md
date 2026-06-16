# V4 Provider Planner Target Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire deterministic evidence-based target-file selection into provider-proposed patch planning when the caller does not supply a target file.

**Architecture:** `ProviderProposedPatchPlanner` will retrieve evidence without a file filter when `target_file=None`, call `EvidenceTargetFileSelector`, and only continue to direct read/provider proposal if the selector returns exactly one clear target. Ambiguous or empty evidence becomes a structured `CapabilityResult` failure before provider calls.

**Tech Stack:** Python dataclasses, pytest, HOM-LLM v4 evidence contracts, `CapabilityResult`, `CapabilityError`.

---

### Task 1: Add Failing Planner Tests

**Files:**
- Modify: `tests/unit/v4/test_provider_patch_planner.py`

- [ ] **Step 1: Make fake retrieval configurable**

Replace `FakeRetrievalService` with:

```python
class FakeRetrievalService:
    def __init__(self, output: EvidenceSet | None = None) -> None:
        self.output = output or evidence_set()
        self.last_request: EvidenceRetrievalRequest | None = None

    def retrieve(self, request: EvidenceRetrievalRequest) -> CapabilityResult[EvidenceSet]:
        self.last_request = request
        return CapabilityResult(
            capability_name="evidence.retrieve",
            ok=True,
            output=self.output,
            error=None,
            telemetry=None,
            artifacts=(),
        )
```

- [ ] **Step 2: Allow request target override**

Change helper signature:

```python
def request(tmp_path: Path, *, target_file: str | None = "calculator.py") -> ProviderProposedPatchPlanRequest:
```

and set `target_file=target_file`.

- [ ] **Step 3: Add selected-target test**

Add:

```python
def test_provider_proposed_patch_planner_selects_target_file_from_retrieved_evidence(
    tmp_path: Path,
) -> None:
    original = "def add(a, b):\n    return a - b\n"
    (tmp_path / "calculator.py").write_text(original, encoding="utf-8")
    retrieval = FakeRetrievalService()
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use addition.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    planner = ProviderProposedPatchPlanner(
        retrieval_service=retrieval,
        direct_read_service=DirectReadService(workspace_root=tmp_path),
        edit_proposer=ProviderBackedEditProposer(provider=provider),
    )

    result = planner.plan(request(tmp_path, target_file=None))

    assert result.ok is True
    assert result.output is not None
    assert result.output.patch_request.patches[0].file_path == "calculator.py"
    assert retrieval.last_request is not None
    assert retrieval.last_request.target_files == ()
```

- [ ] **Step 4: Add ambiguity stop test**

Add:

```python
def test_provider_proposed_patch_planner_stops_before_provider_when_target_selection_ambiguous(
    tmp_path: Path,
) -> None:
    (tmp_path / "calculator.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "helpers.py").write_text("def helper():\n    return None\n", encoding="utf-8")
    ambiguous = EvidenceSet(
        evidence_set_id="evidence-ambiguous",
        query="fix add",
        candidates=(
            EvidenceCandidate(
                candidate_id="cand-1",
                file_path="calculator.py",
                symbol_id=None,
                span_start=1,
                span_end=2,
                content_hash="hash",
                source_channels=("bm25",),
                bm25_score=0.6,
                vector_score=None,
                graph_score=None,
                retrieval_score=0.6,
                metadata={},
            ),
            EvidenceCandidate(
                candidate_id="cand-2",
                file_path="helpers.py",
                symbol_id=None,
                span_start=1,
                span_end=2,
                content_hash="hash",
                source_channels=("bm25",),
                bm25_score=0.55,
                vector_score=None,
                graph_score=None,
                retrieval_score=0.55,
                metadata={},
            ),
        ),
        diagnostics=RetrievalDiagnostics(
            bm25_count=2,
            vector_count=0,
            graph_added_count=0,
            precision_added_count=0,
            coverage_added_count=0,
            retrieval_disagreement=None,
            degraded=False,
            degradation_reason=None,
        ),
    )
    provider = FakeProvider(response_text="provider should not be called")
    planner = ProviderProposedPatchPlanner(
        retrieval_service=FakeRetrievalService(output=ambiguous),
        direct_read_service=DirectReadService(workspace_root=tmp_path),
        edit_proposer=ProviderBackedEditProposer(provider=provider),
    )

    result = planner.plan(request(tmp_path, target_file=None))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "target_selection_ambiguous"
    assert provider.last_request is None
```

- [ ] **Step 5: Run tests to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_patch_planner.py -q
```

Expected: FAIL because `ProviderProposedPatchPlanRequest.target_file` is typed and handled as required, and planner does not select from evidence.

### Task 2: Implement Target Selection in Planner

**Files:**
- Modify: `src/homllm_v4/planning/provider_patch_planner.py`

- [ ] **Step 1: Import error and selector contracts**

Add:

```python
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.planning.target_file_selector import (
    EvidenceTargetFileSelector,
    TargetFileSelectionRequest,
)
```

- [ ] **Step 2: Allow optional target file and selector injection**

Change dataclass field:

```python
    target_file: str | None
```

Change constructor:

```python
        target_selector: EvidenceTargetFileSelector | None = None,
```

Store:

```python
        self.target_selector = target_selector or EvidenceTargetFileSelector()
```

- [ ] **Step 3: Retrieve with optional target filter**

Use:

```python
                target_files=(request.target_file,) if request.target_file else (),
```

- [ ] **Step 4: Resolve target after retrieval**

After retrieval succeeds:

```python
        target_file = request.target_file
        if target_file is None:
            selection = self.target_selector.select(
                TargetFileSelectionRequest(
                    task_id=request.task_id,
                    evidence_set=retrieval.output,
                )
            )
            if selection.decision != "selected" or selection.target_file is None:
                return CapabilityResult(
                    capability_name="patch.plan.provider_proposed",
                    ok=False,
                    output=None,
                    error=CapabilityError(
                        code=(
                            "target_selection_ambiguous"
                            if selection.decision == "ambiguous"
                            else "target_selection_failed"
                        ),
                        message=selection.reason or "target file selection failed",
                        recoverable=True,
                        retryable=False,
                        details={
                            "decision": selection.decision,
                            "candidate_file_scores": selection.candidate_file_scores,
                        },
                    ),
                    telemetry=CapabilityTelemetry(
                        started_at="",
                        ended_at="",
                        duration_ms=0,
                        input_summary={"task_id": request.task_id},
                        output_summary={
                            "selection_decision": selection.decision,
                            "selection_reason": selection.reason,
                        },
                        token_usage={},
                        model_usage={},
                        degraded=False,
                        degradation_reason=None,
                    ),
                    artifacts=(),
                )
            target_file = selection.target_file
```

- [ ] **Step 5: Replace downstream `request.target_file` uses**

Use resolved `target_file` for:

```python
DirectReadRequest.file_path
EditProposalRequest.target_file
candidate.file_path filtering
allowed_file_paths
EvidenceBackedPatchPlanRequest.target_file
```

- [ ] **Step 6: Run planner tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_patch_planner.py -q
```

Expected: all planner tests pass.

### Task 3: Regression and Audit

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Run target selector and planner tests together**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_target_file_selector.py tests\unit\v4\test_provider_patch_planner.py -q
```

- [ ] **Step 2: Run real-index provider patch suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

- [ ] **Step 3: Run full gates**

Run v4 tests, full unit tests, compileall, and forbidden v3 import scan.

- [ ] **Step 4: Update audits**

Record that provider-proposed planning can now select target files from evidence when target is omitted. Keep remaining gap: real-index benchmark still supplies target files and broad autonomous task routing is not done.
