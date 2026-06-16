# V4 Provider Proposal Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist provider edit proposal prompts and raw responses as run artifacts so fake and future live provider patch synthesis can be audited.

**Architecture:** Keep provider proposal logic pure by making artifact writing optional on `ProviderBackedEditProposer`. When an `ArtifactManager` is supplied, the proposer writes prompt/response text artifacts and returns their `ArtifactRef`s in `CapabilityResult.artifacts`; existing callers without an artifact manager behave unchanged.

**Tech Stack:** Python dataclasses, pytest, HOM-LLM v4 `ArtifactManager`, `CapabilityResult.artifacts`.

---

### Task 1: Add Failing Artifact Persistence Test

**Files:**
- Modify: `tests/unit/v4/test_provider_edit_proposer.py`

- [ ] **Step 1: Import artifact manager and pathlib**

Add:

```python
from pathlib import Path

from homllm_v4.artifacts.manager import ArtifactManager
```

- [ ] **Step 2: Add prompt/response artifact test**

Add:

```python
def test_provider_backed_edit_proposer_persists_prompt_and_response_artifacts(
    tmp_path: Path,
) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / "runs")
    manager.create_run("run-1", {"test": "provider artifacts"})
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use addition.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    proposer = ProviderBackedEditProposer(provider=provider, artifact_manager=manager)

    result = proposer.propose(proposal_request())

    assert result.ok is True
    artifact_paths = {artifact.path for artifact in result.artifacts}
    assert "runs/run-1/provider/task-1/prompt.txt" in artifact_paths
    assert "runs/run-1/provider/task-1/response.txt" in artifact_paths
    prompt_text = (tmp_path / "runs" / "run-1" / "provider" / "task-1" / "prompt.txt").read_text(
        encoding="utf-8"
    )
    response_text = (
        tmp_path / "runs" / "run-1" / "provider" / "task-1" / "response.txt"
    ).read_text(encoding="utf-8")
    assert "Expected behavior: add returns a sum" in prompt_text
    assert '"target_file":"calculator.py"' in response_text
```

- [ ] **Step 3: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py::test_provider_backed_edit_proposer_persists_prompt_and_response_artifacts -q
```

Expected: FAIL because `ProviderBackedEditProposer.__init__` does not accept `artifact_manager`.

### Task 2: Implement Optional Provider Artifact Capture

**Files:**
- Modify: `src/homllm_v4/planning/provider_edit_proposer.py`

- [ ] **Step 1: Import artifact types**

Add:

```python
import re

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.artifacts import ArtifactRef
```

- [ ] **Step 2: Store optional artifact manager**

Change constructor:

```python
    def __init__(
        self,
        *,
        provider: EditProposalProvider,
        artifact_manager: ArtifactManager | None = None,
    ) -> None:
        self.provider = provider
        self.artifact_manager = artifact_manager
```

- [ ] **Step 3: Build prompt once and write prompt artifact before provider call**

Inside `propose`, build:

```python
        prompt = build_edit_proposal_prompt(request)
        artifacts = self._write_prompt_artifact(request, prompt)
```

Pass `prompt=prompt` into `ProviderEditProposalRequest`.

- [ ] **Step 4: Write response artifact after provider returns**

After provider response:

```python
            artifacts += self._write_response_artifact(request, provider_response.text)
```

- [ ] **Step 5: Thread artifacts through success and failure results**

Add an `artifacts` parameter to `_failed` and `_with_provider_usage`, then return it on the resulting `CapabilityResult`.

- [ ] **Step 6: Add private artifact helpers**

Add:

```python
    def _write_prompt_artifact(
        self,
        request: EditProposalRequest,
        prompt: str,
    ) -> tuple[ArtifactRef, ...]:
        if self.artifact_manager is None:
            return ()
        return (
            self.artifact_manager.write_text(
                f"provider/{_safe_segment(request.task_id)}/prompt.txt",
                prompt,
                "provider_prompt",
                "provider edit proposal prompt",
            ),
        )

    def _write_response_artifact(
        self,
        request: EditProposalRequest,
        response_text: str,
    ) -> tuple[ArtifactRef, ...]:
        if self.artifact_manager is None:
            return ()
        return (
            self.artifact_manager.write_text(
                f"provider/{_safe_segment(request.task_id)}/response.txt",
                response_text,
                "provider_response",
                "provider edit proposal raw response",
            ),
        )
```

Add module helper:

```python
def _safe_segment(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "task"
```

- [ ] **Step 7: Run provider proposer tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py -q
```

Expected: all tests in the file pass.

### Task 3: Wire Artifacts into Provider-Proposed Planner and Benchmark

**Files:**
- Modify: `src/homllm_v4/planning/provider_patch_planner.py`
- Modify: `src/homllm_v4/evaluation/real_index_provider_suites.py`

- [ ] **Step 1: Allow planner to receive artifact manager**

In `ProviderProposedPatchPlanner.__init__`, accept and store:

```python
        artifact_manager=None,
```

If the supplied `edit_proposer` was constructed without artifacts, do not replace it. This step only prepares the planner to expose artifact manager if future factories need it.

- [ ] **Step 2: Pass artifact manager in real-index benchmark planner construction if the builder supports it**

If this requires broader factory signature churn, defer it. The core artifact behavior is already verified at `ProviderBackedEditProposer`; do not break adapter boundaries.

### Task 4: Verify Regression Gates and Update Audits

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py tests\unit\v4\test_provider_patch_planner.py tests\unit\v4\test_real_index_provider_patch_suite.py -q
```

- [ ] **Step 2: Run full verification gates**

Run v4 tests, full unit tests, compileall, and the forbidden import boundary scan.

- [ ] **Step 3: Update audits**

Record that provider proposal prompt/response artifact capture exists for artifact-manager-backed proposers. Keep the gap honest: live provider synthesis is still not executed in this checkpoint.
