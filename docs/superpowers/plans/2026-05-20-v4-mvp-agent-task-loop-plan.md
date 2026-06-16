# v4 MVP Agent Task Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimum viable local `agent-task` command that runs one bounded repo edit task through live-provider planning, patch application, verification, optional repair, rollback-on-failure, and inspectable artifacts.

**Architecture:** Build a thin orchestration layer over existing v4 components instead of adding a new agent brain. The new API constructs the v3-backed provider planner, `WriteVerifyLoop`, `ProviderWriteVerifyRunner`, and artifact ledger; the CLI only validates arguments and prints a compact JSON result. The first slice assumes the repo is already indexed by the supplied config, preserving current v3 index semantics while making the edit loop usable outside benchmark fixtures.

**Tech Stack:** Python dataclasses, argparse, existing v4 planner/write/verify services, v3 Gemini provider adapter, pytest.

---

## File Structure

- Create `src/homllm_v4/runtime/agent_task.py`
  - Owns `AgentTaskRequest`, `AgentTaskResult`, and `run_agent_task`.
  - Builds provider/planner/write-verify services from injectable builders.
  - Produces result fields suitable for CLI JSON and artifact inspection.
- Modify `src/homllm_v4/api.py`
  - Re-export `run_agent_task`, `AgentTaskRequest`, and `AgentTaskResult`.
- Modify `src/homllm_v4/cli.py`
  - Add `agent-task` subcommand.
  - Default model to `gemini-3.1-flash-lite-preview`.
  - Require `--live-api-key-env` for live mode unless a test/injected API path bypasses it.
- Create `tests/unit/v4/test_agent_task.py`
  - API-level tests with fake provider/planner dependencies and a tiny workspace.
- Modify `tests/unit/v4/test_provider_fixture_cli.py`
  - CLI propagation tests for `agent-task`.
- Update `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Record the new MVP loop surface and caveats after verification.

## Task 1: Agent Task API Contract

**Files:**
- Create: `tests/unit/v4/test_agent_task.py`
- Create: `src/homllm_v4/runtime/agent_task.py`
- Modify: `src/homllm_v4/api.py`

- [x] **Step 1: Write the failing API smoke test**

Create `tests/unit/v4/test_agent_task.py` with a focused test that proves a non-benchmark caller can run one edit/verify task through the existing runner.

```python
import json
import sys
from pathlib import Path

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.evidence import (
    EvidenceCandidate,
    EvidenceRetrievalRequest,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.planning.provider_edit_proposer import (
    ProviderBackedEditProposer,
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
)
from homllm_v4.planning.provider_patch_planner import ProviderProposedPatchPlanner
from homllm_v4.runtime.agent_task import AgentTaskRequest, run_agent_task
from homllm_v4.services.direct_read_service import DirectReadService


class SingleFileRetrievalService:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root

    def retrieve(self, request: EvidenceRetrievalRequest) -> CapabilityResult[EvidenceSet]:
        target_file = request.target_files[0]
        content = (self.workspace_root / target_file).read_text(encoding="utf-8")
        return CapabilityResult(
            capability_name="evidence.retrieve",
            ok=True,
            output=EvidenceSet(
                evidence_set_id=f"{request.task_id}:evidence",
                query=request.query,
                candidates=(
                    EvidenceCandidate(
                        candidate_id=f"{request.task_id}:candidate:{target_file}",
                        file_path=target_file,
                        symbol_id=None,
                        span_start=1,
                        span_end=len(content.splitlines()),
                        content_hash="hash",
                        source_channels=("test",),
                        bm25_score=None,
                        vector_score=None,
                        graph_score=None,
                        retrieval_score=1.0,
                        metadata={"content": content},
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
            ),
            error=None,
            telemetry=None,
            artifacts=(),
        )


class ReplacingProvider:
    def propose_edit(self, request: ProviderEditProposalRequest) -> ProviderEditProposalResponse:
        new_content = request.current_content.replace("return text.upper()", "return text.strip().upper()")
        return ProviderEditProposalResponse(
            text=json.dumps(
                {
                    "target_file": request.target_file,
                    "new_content": new_content,
                    "rationale": "Strip whitespace before uppercasing.",
                    "evidence_ids": list(request.evidence_ids),
                    "risk_flags": [],
                }
            ),
            tokens_in=10,
            tokens_out=5,
            model="fake-test",
            metadata={"provider": "test"},
        )


def test_run_agent_task_applies_and_verifies_single_live_style_edit(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "sku.py").write_text(
        "def normalize(text: str) -> str:\n    return text.upper()\n",
        encoding="utf-8",
    )

    def build_provider(**kwargs):
        return ReplacingProvider()

    def build_planner(**kwargs):
        root = Path(kwargs["workspace_root"])
        return ProviderProposedPatchPlanner(
            retrieval_service=SingleFileRetrievalService(root),
            direct_read_service=DirectReadService(workspace_root=root),
            edit_proposer=ProviderBackedEditProposer(
                provider=kwargs["edit_provider"],
                artifact_manager=kwargs["artifact_manager"],
                max_prompt_chars=kwargs["max_prompt_chars"],
            ),
        )

    result = run_agent_task(
        AgentTaskRequest(
            config_path=tmp_path / "config.yaml",
            workspace_root=workspace,
            artifact_root=tmp_path / "runs",
            run_id="agent-task-test",
            query="normalize should strip whitespace before uppercasing",
            intent="Make normalize strip surrounding whitespace before uppercasing.",
            expected_behavior="normalize(' sku ') returns 'SKU'.",
            target_file="sku.py",
            verification_argv=(
                sys.executable,
                "-c",
                "from sku import normalize; raise SystemExit(0 if normalize(' sku ') == 'SKU' else 1)",
            ),
            live_api_key="test-key",
            provider_builder=build_provider,
            planner_builder=build_planner,
        )
    )

    assert result.stop_reason == "verified"
    assert result.error_code is None
    assert result.patch_attempt_count == 1
    assert result.verification_count == 1
    assert "strip().upper()" in (workspace / "sku.py").read_text(encoding="utf-8")
    assert (tmp_path / "runs" / "agent-task-test" / "provider" / "agent-task-test" / "prompt.txt").is_file()
```

- [x] **Step 2: Run the API test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_task.py::test_run_agent_task_applies_and_verifies_single_live_style_edit -q
```

Expected: fail because `homllm_v4.runtime.agent_task` does not exist.

- [x] **Step 3: Implement minimal API**

Create `src/homllm_v4/runtime/agent_task.py`:

```python
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
import sys

from homllm_v4.adapters.v3_provider_factory import build_v3_provider_edit_adapter_from_params
from homllm_v4.adapters.v3_provider_patch_factory import build_v3_provider_proposed_patch_planner
from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.command import CommandPolicy
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.planning.provider_patch_planner import ProviderProposedPatchPlanRequest
from homllm_v4.runtime.provider_write_verify_runner import (
    ProviderWriteVerifyRunner,
    ProviderWriteVerifyRunRequest,
)
from homllm_v4.runtime.write_verify_loop import WriteVerifyLoop
from homllm_v4.services.command_service import LocalCommandService
from homllm_v4.services.patch_service import WorkspacePatchService


@dataclass(frozen=True)
class AgentTaskRequest:
    config_path: Path
    workspace_root: Path
    artifact_root: Path
    query: str
    intent: str
    expected_behavior: str
    target_file: str | None
    verification_argv: tuple[str, ...]
    run_id: str | None = None
    live_provider_name: str = "gemini"
    live_model: str = "gemini-3.1-flash-lite-preview"
    live_api_key: str | None = None
    live_max_output_tokens: int = 8192
    max_prompt_chars: int | None = 22000
    provider_repair_attempts: int = 1
    smoke_safe: bool = True
    provider_builder = build_v3_provider_edit_adapter_from_params
    planner_builder = build_v3_provider_proposed_patch_planner


@dataclass(frozen=True)
class AgentTaskResult:
    run_id: str
    stop_reason: str
    error_code: str | None
    artifact_root: str
    patch_attempt_count: int
    provider_repair_attempt_count: int
    verification_count: int
    planner_metrics: dict[str, object]


def run_agent_task(request: AgentTaskRequest) -> AgentTaskResult:
    if not request.live_api_key:
        raise ValueError("live_provider_api_key_required")
    if not request.verification_argv:
        raise ValueError("verification_argv_required")

    run_id = request.run_id or str(uuid4())
    workspace_root = Path(request.workspace_root).resolve()
    artifact_root = Path(request.artifact_root).resolve()
    artifact_manager = ArtifactManager(workspace_root=workspace_root, artifact_root=artifact_root)
    artifact_manager.create_run(
        run_id,
        {
            "entrypoint": "homllm_v4.runtime.agent_task.run_agent_task",
            "query": request.query,
            "target_file": request.target_file,
        },
    )
    loop = WriteVerifyLoop(
        patch_service=WorkspacePatchService(),
        command_service=LocalCommandService(
            policy=CommandPolicy(
                allowed_executables=(Path(sys.executable).name,),
                default_timeout_seconds=30,
                max_timeout_seconds=60,
            )
        ),
        artifact_manager=artifact_manager,
        event_writer=EventWriter(artifact_root / run_id / "events.jsonl"),
    )
    provider = request.provider_builder(
        provider_name=request.live_provider_name,
        model=request.live_model,
        api_key=request.live_api_key,
        temperature=0.0,
        max_output_tokens=request.live_max_output_tokens,
    )
    planner = request.planner_builder(
        config_path=Path(request.config_path),
        workspace_root=workspace_root,
        edit_provider=provider,
        smoke_safe=request.smoke_safe,
        artifact_manager=artifact_manager,
        max_prompt_chars=request.max_prompt_chars,
    )
    result = ProviderWriteVerifyRunner(planner=planner, write_verify_loop=loop).run(
        ProviderWriteVerifyRunRequest(
            task_id=run_id,
            run_id=run_id,
            workspace_root=str(workspace_root),
            plan_request=ProviderProposedPatchPlanRequest(
                task_id=run_id,
                workspace_root=str(workspace_root),
                query=request.query,
                task_class="mvp_agent_task",
                index_id=f"{run_id}:index",
                target_file=request.target_file,
                intent=request.intent,
                expected_behavior=request.expected_behavior,
                verification_argv=request.verification_argv,
                retrieval_policy={"intent": "PATCH", "top_k": 20},
            ),
            max_verification_commands=1,
            provider_repair_attempts=request.provider_repair_attempts,
            rollback_on_failure=True,
        )
    )
    return AgentTaskResult(
        run_id=run_id,
        stop_reason=result.stop_reason,
        error_code=result.error_code,
        artifact_root=str(artifact_root),
        patch_attempt_count=result.patch_attempt_count,
        provider_repair_attempt_count=result.provider_repair_attempt_count,
        verification_count=len(result.verification_results),
        planner_metrics=result.planner_metrics,
    )
```

Also re-export the API in `src/homllm_v4/api.py`.

- [x] **Step 4: Run the API test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_task.py::test_run_agent_task_applies_and_verifies_single_live_style_edit -q
```

Expected: pass.

## Task 2: CLI Subcommand

**Files:**
- Modify: `src/homllm_v4/cli.py`
- Modify: `tests/unit/v4/test_provider_fixture_cli.py`

- [x] **Step 1: Write the failing CLI propagation test**

Add:

```python
def test_cli_runs_agent_task_with_live_defaults(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    class Result:
        run_id = "agent-cli-test"
        stop_reason = "verified"
        error_code = None
        artifact_root = str(tmp_path / "runs")
        patch_attempt_count = 1
        provider_repair_attempt_count = 0
        verification_count = 1
        planner_metrics = {"provider_tokens_in": 10}

    def fake_run(request):
        captured["request"] = request
        return Result()

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr("homllm_v4.cli.run_agent_task", fake_run)

    result = main(
        [
            "agent-task",
            "--config", "config.yaml",
            "--workspace-root", str(tmp_path),
            "--artifact-root", str(tmp_path / "runs"),
            "--query", "fix normalize whitespace",
            "--intent", "Strip whitespace before uppercasing.",
            "--expected-behavior", "normalize(' sku ') returns 'SKU'.",
            "--target-file", "sku.py",
            "--verification-cmd", f"{sys.executable} -m compileall -q sku.py",
            "--live-api-key-env", "GOOGLE_API_KEY",
        ]
    )

    assert result == 0
    assert captured["request"].live_model == "gemini-3.1-flash-lite-preview"
    assert captured["request"].live_api_key == "test-key"
    assert captured["request"].target_file == "sku.py"
```

- [x] **Step 2: Run the CLI test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_runs_agent_task_with_live_defaults -q
```

Expected: fail because `agent-task` does not exist.

- [x] **Step 3: Implement CLI command**

Add parser:

```python
agent_task = subparsers.add_parser("agent-task", help="run one bounded v4 MVP coding-agent task")
agent_task.add_argument("--config", required=True)
agent_task.add_argument("--workspace-root", required=True)
agent_task.add_argument("--artifact-root", required=True)
agent_task.add_argument("--run-id")
agent_task.add_argument("--query", required=True)
agent_task.add_argument("--intent", required=True)
agent_task.add_argument("--expected-behavior", required=True)
agent_task.add_argument("--target-file")
agent_task.add_argument("--verification-cmd", required=True)
agent_task.add_argument("--live-provider", default="gemini")
agent_task.add_argument("--live-model", default="gemini-3.1-flash-lite-preview")
agent_task.add_argument("--live-max-output-tokens", type=int, default=8192)
agent_task.add_argument("--live-api-key-env", required=True)
agent_task.add_argument("--max-prompt-chars", type=int, default=22000)
agent_task.add_argument("--provider-repair-attempts", type=int, default=1)
agent_task.add_argument("--smoke-safe", action="store_true")
```

Use `shlex.split(args.verification_cmd)` to produce `verification_argv`, call `run_agent_task`, and print JSON with run id, stop reason, error code, artifact root, counts, and planner metrics. Return `0` only when `stop_reason == "verified"` and no error code.

- [x] **Step 4: Run the CLI test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_fixture_cli.py::test_cli_runs_agent_task_with_live_defaults -q
```

Expected: pass.

## Task 3: Focused Verification And Audit

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [x] **Step 1: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_task.py tests\unit\v4\test_provider_fixture_cli.py -q
```

Expected: pass.

- [x] **Step 2: Run compile verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py
```

Expected: pass.

- [x] **Step 3: Update active-goal audit**

Record that v4 now has a first MVP local edit command. Caveat: first slice assumes a matching index already exists for the supplied config; automatic indexing and live end-to-end proof remain next work.
