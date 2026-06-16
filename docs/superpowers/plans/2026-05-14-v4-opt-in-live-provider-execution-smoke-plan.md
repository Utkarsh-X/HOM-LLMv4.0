# v4 Opt-In Live Provider Execution Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add skipped-by-default live-provider validation that a provider-synthesized patch can pass through v4 planning, patch application, and verification in a temporary fixture workspace.

**Architecture:** The live provider remains behind `HOMLLM_V4_RUN_LIVE_PROVIDER_SMOKE=1`. The test uses the existing v3 provider adapter factory, a fixture retrieval service, `ProviderProposedPatchPlanner`, `WorkspacePatchService`, `LocalCommandService`, and `WriteVerifyLoop`; normal verification imports the test but skips the live call.

**Tech Stack:** Python, pytest, v4 provider planner, v4 write/verify loop, existing v3 Gemini/OpenAI provider connectors.

---

## File Structure

- Modify: `tests/unit/v4/test_live_provider_edit_smoke.py`
  - Add local fixture evidence service and content hash helper.
  - Add opt-in live provider execution smoke using `fixtures/v4/python_patch_repo`.
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - Record that the live execution smoke scaffold exists but was not run during normal verification.
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Update checklist and remaining gaps.

No production code should change unless the test exposes a real import/API defect.

---

### Task 1: Add the Skipped-by-Default Live Execution Smoke

**Files:**
- Modify: `tests/unit/v4/test_live_provider_edit_smoke.py`

- [ ] **Step 1: Add imports**

Add these imports:

```python
import hashlib
import shutil
import sys
from pathlib import Path
```

Add these v4 imports:

```python
from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.command import CommandPolicy, CommandRunRequest
from homllm_v4.contracts.evidence import (
    DirectReadResult,
    EvidenceCandidate,
    EvidenceRetrievalRequest,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.contracts.write_loop import WriteVerifyLoopRequest
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.planning.provider_patch_planner import (
    ProviderProposedPatchPlanRequest,
    ProviderProposedPatchPlanner,
)
from homllm_v4.runtime.write_verify_loop import WriteVerifyLoop
from homllm_v4.services.command_service import LocalCommandService
from homllm_v4.services.direct_read_service import DirectReadService
from homllm_v4.services.patch_service import WorkspacePatchService
```

- [ ] **Step 2: Add local fixture helpers**

Add these helpers after imports:

```python
def _content_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


class _FixtureRetrievalService:
    def __init__(self, evidence: EvidenceSet) -> None:
        self.evidence = evidence

    def retrieve(self, request: EvidenceRetrievalRequest) -> CapabilityResult[EvidenceSet]:
        return CapabilityResult(
            capability_name="evidence.retrieve",
            ok=True,
            output=self.evidence,
            error=None,
            telemetry=None,
            artifacts=(),
        )


def _calculator_evidence_set(content: str) -> EvidenceSet:
    return EvidenceSet(
        evidence_set_id="live-provider-exec:evidence",
        query="fix calculator add",
        candidates=(
            EvidenceCandidate(
                candidate_id="live-provider-exec:candidate:calculator.py",
                file_path="calculator.py",
                symbol_id=None,
                span_start=1,
                span_end=max(1, len(content.splitlines())),
                content_hash=_content_hash(content),
                source_channels=("fixture",),
                bm25_score=None,
                vector_score=None,
                graph_score=None,
                retrieval_score=1.0,
                metadata={"case_id": "live-provider-exec"},
            ),
        ),
        diagnostics=RetrievalDiagnostics(
            bm25_count=1,
            vector_count=0,
            graph_added_count=0,
            precision_added_count=0,
            coverage_added_count=0,
            retrieval_disagreement=None,
            degraded=False,
            degradation_reason=None,
        ),
    )
```

- [ ] **Step 3: Add live execution smoke**

Add this test after `test_live_provider_can_return_bounded_edit_proposal_json`:

```python
def test_live_provider_patch_can_apply_and_verify_in_fixture_workspace(tmp_path: Path) -> None:
    if os.getenv("HOMLLM_V4_RUN_LIVE_PROVIDER_SMOKE") != "1":
        pytest.skip("set HOMLLM_V4_RUN_LIVE_PROVIDER_SMOKE=1 to run live provider smoke")

    provider_name = os.getenv("HOMLLM_V4_LIVE_PROVIDER", "gemini")
    model = os.getenv("HOMLLM_V4_LIVE_MODEL", "gemini-2.5-flash")
    api_key = os.getenv("HOMLLM_V4_LIVE_PROVIDER_API_KEY")
    fixture_root = Path("fixtures/v4/python_patch_repo").resolve()
    workspace_root = tmp_path / "workspace"
    shutil.copytree(fixture_root, workspace_root)
    current_content = (workspace_root / "calculator.py").read_text(encoding="utf-8")

    adapter = build_v3_provider_edit_adapter(
        provider_name=provider_name,
        model=model,
        model_config=ModelConfig(temperature=0.0, max_output_tokens=2048),
        api_key=api_key,
    )
    planner = ProviderProposedPatchPlanner(
        retrieval_service=_FixtureRetrievalService(_calculator_evidence_set(current_content)),
        direct_read_service=DirectReadService(workspace_root=workspace_root),
        edit_proposer=ProviderBackedEditProposer(provider=adapter),
    )
    plan_result = planner.plan(
        ProviderProposedPatchPlanRequest(
            task_id="live-provider-exec",
            workspace_root=str(workspace_root),
            query="Fix calculator.add so it returns the sum instead of subtracting.",
            task_class="python_patch",
            index_id="live-provider-exec:fixture-index",
            target_file="calculator.py",
            intent="Fix calculator.add by changing subtraction to addition only.",
            expected_behavior="calculator.add(2, 3) returns 5 and existing pytest tests pass.",
            verification_argv=(sys.executable, "-m", "pytest", ".", "-q"),
            retrieval_policy={"intent": "PATCH", "top_k": 1},
            expected_content_hash=_content_hash(current_content),
        )
    )
    if not plan_result.ok:
        pytest.fail(f"live provider patch plan failed: {plan_result.error}")
    assert plan_result.output is not None

    manager = ArtifactManager(
        workspace_root=workspace_root,
        artifact_root=tmp_path / ".homllm" / "runs",
    )
    manager.create_run("live-provider-exec", {})
    loop = WriteVerifyLoop(
        patch_service=WorkspacePatchService(),
        command_service=LocalCommandService(
            policy=CommandPolicy(
                allowed_executables=(Path(sys.executable).name,),
                default_timeout_seconds=20,
                max_timeout_seconds=20,
            )
        ),
        artifact_manager=manager,
        event_writer=EventWriter(tmp_path / ".homllm" / "runs" / "live-provider-exec" / "events.jsonl"),
    )

    result = loop.run(
        WriteVerifyLoopRequest(
            task_id="live-provider-exec",
            run_id="live-provider-exec",
            workspace_root=str(workspace_root),
            patch_request=plan_result.output.patch_request,
            verification_commands=(
                CommandRunRequest(
                    task_id="live-provider-exec",
                    workspace_root=str(workspace_root),
                    cwd=".",
                    argv=(sys.executable, "-m", "pytest", ".", "-q"),
                    timeout_seconds=20,
                ),
            ),
            max_verification_commands=1,
            max_patch_attempts=1,
            rollback_on_failure=True,
        )
    )

    assert result.stop_reason == "verified"
    assert "return a + b" in (workspace_root / "calculator.py").read_text(encoding="utf-8")
```

- [ ] **Step 4: Run default targeted test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_live_provider_edit_smoke.py -q
```

Expected: both live tests are skipped unless `HOMLLM_V4_RUN_LIVE_PROVIDER_SMOKE=1`.

---

### Task 2: Verification Gate

**Files:**
- No production files expected.

- [ ] **Step 1: Run v4 unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
```

Expected: all pass, live tests skipped by default.

- [ ] **Step 2: Run full unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
```

Expected: all pass, live tests skipped by default.

- [ ] **Step 3: Run compile and import boundary checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected:

- compile exits `0`
- boundary scan returns no output

---

### Task 3: Update Audits

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Record scaffold status**

Add that the live provider patch execution smoke exists and is skipped by default.

- [ ] **Step 2: Keep live result gap explicit**

State that this checkpoint did not run the live provider smoke because normal verification is network-free and no provider key is assumed.

---

## Self-Review

Spec coverage:

- This plan adds the smallest next live-provider scaffold: provider proposal, evidence-scoped planning, patch application, and verification in a copied fixture workspace.
- It does not run live providers by default.
- It does not add autonomous file selection or real-index benchmarking.

Placeholder scan:

- No placeholder task remains. Commands and paths are concrete.

Type consistency:

- The test uses existing v4 contracts and services only.
- v3 provider construction stays inside `src/homllm_v4/adapters/v3_provider_factory.py`.

