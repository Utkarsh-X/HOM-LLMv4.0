import hashlib
import shutil
import sys
from pathlib import Path
from uuid import uuid4

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.command import CommandPolicy
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.evaluation import CaseExecutionResult, EvaluationCase, EvaluationRunResult
from homllm_v4.contracts.evidence import (
    DirectReadResult,
    EvidenceCandidate,
    EvidenceRetrievalRequest,
    EvidenceSet,
    RetrievalDiagnostics,
)
from homllm_v4.contracts.write_loop import WriteVerifyLoopRequest
from homllm_v4.evaluation.harness import V4EvaluationHarness
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.planning.evidence_patch_planner import (
    EvidenceBackedPatchPlanRequest,
    EvidenceBackedPatchPlanner,
)
from homllm_v4.planning.provider_edit_proposer import (
    ProviderBackedEditProposer,
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
)
from homllm_v4.planning.provider_patch_planner import (
    ProviderProposedPatchPlanRequest,
    ProviderProposedPatchPlanner,
)
from homllm_v4.runtime.write_verify_loop import WriteVerifyLoop
from homllm_v4.services.command_service import LocalCommandService
from homllm_v4.services.direct_read_service import DirectReadService
from homllm_v4.services.patch_service import WorkspacePatchService


def run_python_patch_fixture_suite(
    *,
    fixture_root: Path,
    workspace_root: Path,
    artifact_root: Path,
    run_id: str | None = None,
) -> EvaluationRunResult:
    resolved_run_id = run_id or str(uuid4())
    fixture_root = Path(fixture_root).resolve()
    workspace_root = Path(workspace_root).resolve()
    artifact_root = Path(artifact_root).resolve()
    original = (fixture_root / "calculator.py").read_text(encoding="utf-8")
    fixed = original.replace("return a - b", "return a + b")
    wrong_but_valid = original.replace("return a - b", "return a * b")
    cases = (
        _case(
            case_id="verified-fix",
            original=original,
            new_content=fixed,
            expected_stop_reason="verified",
        ),
        _case(
            case_id="stale-context",
            original=fixed,
            new_content=fixed,
            expected_stop_reason="patch_failed",
            expected_error_code="stale_context",
        ),
        EvaluationCase(
            case_id="unexpected-file",
            runner_id="write_verify",
            task_type="python_patch",
            input_payload={
                "file_path": "side_effect.py",
                "expected_content_hash": None,
                "new_content": "SIDE_EFFECT = True\n",
                "allowed_file_paths": ("calculator.py",),
                "verification_argv": (sys.executable, "-m", "pytest", ".", "-q"),
            },
            expected_stop_reason="patch_failed",
            expected_error_code="diff_inspection_failed",
        ),
        _case(
            case_id="repair-budget",
            original=original,
            new_content=wrong_but_valid,
            expected_stop_reason="repair_budget_exhausted",
            max_patch_attempts=2,
        ),
    )
    artifact_manager = ArtifactManager(
        workspace_root=workspace_root,
        artifact_root=artifact_root,
    )
    artifact_manager.create_run(
        resolved_run_id,
        {
            "entrypoint": "homllm_v4.evaluation.fixture_suites.run_python_patch_fixture_suite",
            "fixture_root": str(fixture_root),
            "case_count": len(cases),
        },
    )
    loop = WriteVerifyLoop(
        patch_service=WorkspacePatchService(),
        command_service=LocalCommandService(
            policy=CommandPolicy(
                allowed_executables=(Path(sys.executable).name,),
                default_timeout_seconds=10,
                max_timeout_seconds=10,
            )
        ),
        artifact_manager=artifact_manager,
        event_writer=EventWriter(artifact_root / resolved_run_id / "events.jsonl"),
    )

    def run_case(case: EvaluationCase) -> CaseExecutionResult:
        case_workspace = _copy_case_workspace(
            fixture_root=fixture_root,
            workspace_root=workspace_root,
            run_id=resolved_run_id,
            case_id=case.case_id,
        )
        request_result = _build_evidence_backed_request(case, case_workspace, resolved_run_id)
        if isinstance(request_result, CaseExecutionResult):
            return request_result
        result = loop.run(request_result)
        output_chars = sum(
            len(command.stdout or "") + len(command.stderr or "")
            for command in result.verification_results
        )
        return CaseExecutionResult(
            stop_reason=result.stop_reason,
            metrics={
                "patch_attempt_count": result.patch_attempt_count,
                "verification_count": len(result.verification_results),
                "verification_duration_ms": sum(
                    int(command.duration_ms) for command in result.verification_results
                ),
                "verification_output_chars": output_chars,
                "verification_output_token_estimate": output_chars // 4,
            },
            error_code=result.error.code if result.error else None,
        )

    harness = V4EvaluationHarness(
        artifact_manager=artifact_manager,
        runners={"write_verify": run_case},
    )
    return harness.run(run_id=resolved_run_id, cases=cases)


def run_python_provider_patch_fixture_suite(
    *,
    fixture_root: Path,
    workspace_root: Path,
    artifact_root: Path,
    run_id: str | None = None,
) -> EvaluationRunResult:
    resolved_run_id = run_id or str(uuid4())
    fixture_root = Path(fixture_root).resolve()
    workspace_root = Path(workspace_root).resolve()
    artifact_root = Path(artifact_root).resolve()
    original = (fixture_root / "calculator.py").read_text(encoding="utf-8")
    fixed = original.replace("return a - b", "return a + b")

    cases = (
        EvaluationCase(
            case_id="provider-verified-fix",
            runner_id="provider_write_verify",
            task_type="python_provider_patch",
            input_payload={
                "file_path": "calculator.py",
                "expected_content_hash": _content_hash(original),
                "provider_new_content": fixed,
                "provider_evidence_ids": ("provider-verified-fix:candidate:calculator.py",),
                "verification_argv": (sys.executable, "-m", "pytest", ".", "-q"),
            },
            expected_stop_reason="verified",
        ),
        EvaluationCase(
            case_id="provider-unknown-evidence",
            runner_id="provider_write_verify",
            task_type="python_provider_patch",
            input_payload={
                "file_path": "calculator.py",
                "expected_content_hash": _content_hash(original),
                "provider_new_content": fixed,
                "provider_evidence_ids": ("unknown",),
                "verification_argv": (sys.executable, "-m", "pytest", ".", "-q"),
            },
            expected_stop_reason="patch_failed",
            expected_error_code="proposal_evidence_scope_denied",
        ),
    )
    artifact_manager = ArtifactManager(
        workspace_root=workspace_root,
        artifact_root=artifact_root,
    )
    artifact_manager.create_run(
        resolved_run_id,
        {
            "entrypoint": "homllm_v4.evaluation.fixture_suites.run_python_provider_patch_fixture_suite",
            "fixture_root": str(fixture_root),
            "case_count": len(cases),
        },
    )
    loop = WriteVerifyLoop(
        patch_service=WorkspacePatchService(),
        command_service=LocalCommandService(
            policy=CommandPolicy(
                allowed_executables=(Path(sys.executable).name,),
                default_timeout_seconds=10,
                max_timeout_seconds=10,
            )
        ),
        artifact_manager=artifact_manager,
        event_writer=EventWriter(artifact_root / resolved_run_id / "events.jsonl"),
    )

    def run_case(case: EvaluationCase) -> CaseExecutionResult:
        case_workspace = _copy_case_workspace(
            fixture_root=fixture_root,
            workspace_root=workspace_root,
            run_id=resolved_run_id,
            case_id=case.case_id,
        )
        planner_result, provider = _build_provider_proposed_plan(case, case_workspace)
        if not planner_result.ok or planner_result.output is None:
            return CaseExecutionResult(
                stop_reason="patch_failed",
                metrics={
                    "patch_attempt_count": 0,
                    "verification_count": 0,
                    "verification_duration_ms": 0,
                    "verification_output_chars": 0,
                    "verification_output_token_estimate": 0,
                    "provider_tokens_in": provider.tokens_in,
                    "provider_tokens_out": provider.tokens_out,
                },
                error_code=planner_result.error.code if planner_result.error else "patch_plan_failed",
            )

        max_patch_attempts = case.input_payload.get("max_patch_attempts", 1)
        result = loop.run(
            WriteVerifyLoopRequest(
                task_id=case.case_id,
                run_id=resolved_run_id,
                workspace_root=str(case_workspace),
                patch_request=planner_result.output.patch_request,
                verification_commands=planner_result.output.verification_commands,
                max_verification_commands=1,
                max_patch_attempts=max_patch_attempts if isinstance(max_patch_attempts, int) else 1,
            )
        )
        output_chars = sum(
            len(command.stdout or "") + len(command.stderr or "")
            for command in result.verification_results
        )
        return CaseExecutionResult(
            stop_reason=result.stop_reason,
            metrics={
                "patch_attempt_count": result.patch_attempt_count,
                "verification_count": len(result.verification_results),
                "verification_duration_ms": sum(
                    int(command.duration_ms) for command in result.verification_results
                ),
                "verification_output_chars": output_chars,
                "verification_output_token_estimate": output_chars // 4,
                "provider_tokens_in": provider.tokens_in,
                "provider_tokens_out": provider.tokens_out,
            },
            error_code=result.error.code if result.error else None,
        )

    harness = V4EvaluationHarness(
        artifact_manager=artifact_manager,
        runners={"provider_write_verify": run_case},
    )
    return harness.run(run_id=resolved_run_id, cases=cases)


def _case(
    *,
    case_id: str,
    original: str,
    new_content: str,
    expected_stop_reason: str,
    expected_error_code: str | None = None,
    max_patch_attempts: int = 1,
) -> EvaluationCase:
    return EvaluationCase(
        case_id=case_id,
        runner_id="write_verify",
        task_type="python_patch",
        input_payload={
            "file_path": "calculator.py",
            "expected_content_hash": _content_hash(original),
            "new_content": new_content,
            "allowed_file_paths": ("calculator.py",),
            "verification_argv": (sys.executable, "-m", "pytest", ".", "-q"),
            "max_patch_attempts": max_patch_attempts,
        },
        expected_stop_reason=expected_stop_reason,
        expected_error_code=expected_error_code,
    )


def _copy_case_workspace(
    *,
    fixture_root: Path,
    workspace_root: Path,
    run_id: str,
    case_id: str,
) -> Path:
    target = workspace_root / run_id / "cases" / case_id
    if target.exists():
        raise ValueError(f"case_workspace_exists: {target}")
    shutil.copytree(fixture_root, target)
    return target


def _build_evidence_backed_request(
    case: EvaluationCase,
    workspace_root: Path,
    run_id: str,
) -> WriteVerifyLoopRequest | CaseExecutionResult:
    payload = case.input_payload
    target_file = str(payload["file_path"])
    target_path = workspace_root / target_file
    if target_path.exists():
        content = target_path.read_text(encoding="utf-8")
        direct_hash = _content_hash(content)
    else:
        content = ""
        direct_hash = None

    planner_result = EvidenceBackedPatchPlanner().plan(
        EvidenceBackedPatchPlanRequest(
            task_id=case.case_id,
            workspace_root=str(workspace_root),
            target_file=target_file,
            intent=f"fixture case {case.case_id}",
            expected_behavior=case.expected_stop_reason,
            evidence_set=_single_file_evidence_set(case, target_file, content),
            direct_reads=(
                DirectReadResult(
                    file_path=target_file,
                    content_excerpt=content,
                    line_start=None,
                    line_end=None,
                    content_hash=direct_hash,
                    truncated=False,
                    freshness="fresh",
                ),
            ),
            expected_content_hash=payload.get("expected_content_hash") if isinstance(payload.get("expected_content_hash"), str) else None,
            new_content=str(payload["new_content"]),
            verification_argv=tuple(str(part) for part in payload["verification_argv"]),
            allowed_file_paths=tuple(str(path) for path in payload.get("allowed_file_paths", (target_file,))),
        )
    )
    if not planner_result.ok or planner_result.output is None:
        return CaseExecutionResult(
            stop_reason="patch_failed",
            metrics={
                "patch_attempt_count": 0,
                "verification_count": 0,
                "verification_duration_ms": 0,
                "verification_output_chars": 0,
                "verification_output_token_estimate": 0,
            },
            error_code=planner_result.error.code if planner_result.error else "patch_plan_failed",
        )

    max_patch_attempts = payload.get("max_patch_attempts", 1)
    return WriteVerifyLoopRequest(
        task_id=case.case_id,
        run_id=run_id,
        workspace_root=str(workspace_root),
        patch_request=planner_result.output.patch_request,
        verification_commands=planner_result.output.verification_commands,
        max_verification_commands=1,
        max_patch_attempts=max_patch_attempts if isinstance(max_patch_attempts, int) else 1,
    )


def _build_provider_proposed_plan(
    case: EvaluationCase,
    workspace_root: Path,
):
    payload = case.input_payload
    target_file = str(payload["file_path"])
    target_path = workspace_root / target_file
    content = target_path.read_text(encoding="utf-8")
    evidence = _single_file_evidence_set(case, target_file, content)
    provider = _FixtureEditProvider(
        target_file=target_file,
        new_content=str(payload["provider_new_content"]),
        evidence_ids=tuple(str(item) for item in payload["provider_evidence_ids"]),
    )
    planner = ProviderProposedPatchPlanner(
        retrieval_service=_FixtureRetrievalService(evidence),
        direct_read_service=DirectReadService(workspace_root=workspace_root),
        edit_proposer=ProviderBackedEditProposer(provider=provider),
    )
    return (
        planner.plan(
            ProviderProposedPatchPlanRequest(
                task_id=case.case_id,
                workspace_root=str(workspace_root),
                query=f"fixture provider case {case.case_id}",
                task_class=case.task_type,
                index_id=f"{case.case_id}:fixture-index",
                target_file=target_file,
                intent=f"fixture provider case {case.case_id}",
                expected_behavior=case.expected_stop_reason,
                verification_argv=tuple(str(part) for part in payload["verification_argv"]),
                retrieval_policy={"intent": "PATCH", "top_k": 1},
                expected_content_hash=payload.get("expected_content_hash") if isinstance(payload.get("expected_content_hash"), str) else None,
            )
        ),
        provider,
    )


def _single_file_evidence_set(
    case: EvaluationCase,
    target_file: str,
    content: str,
) -> EvidenceSet:
    return EvidenceSet(
        evidence_set_id=f"{case.case_id}:evidence",
        query=f"fixture case {case.case_id}",
        candidates=(
            EvidenceCandidate(
                candidate_id=f"{case.case_id}:candidate:{target_file}",
                file_path=target_file,
                symbol_id=None,
                span_start=1,
                span_end=max(1, len(content.splitlines())),
                content_hash=_content_hash(content),
                source_channels=("fixture",),
                bm25_score=None,
                vector_score=None,
                graph_score=None,
                retrieval_score=1.0,
                metadata={"case_id": case.case_id},
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


class _FixtureEditProvider:
    tokens_in = 13
    tokens_out = 9

    def __init__(
        self,
        *,
        target_file: str,
        new_content: str,
        evidence_ids: tuple[str, ...],
    ) -> None:
        self.target_file = target_file
        self.new_content = new_content
        self.evidence_ids = evidence_ids

    def propose_edit(self, request: ProviderEditProposalRequest) -> ProviderEditProposalResponse:
        import json

        return ProviderEditProposalResponse(
            text=json.dumps(
                {
                    "target_file": self.target_file,
                    "new_content": self.new_content,
                    "rationale": "Fixture provider proposes the requested calculator patch.",
                    "evidence_ids": list(self.evidence_ids),
                    "risk_flags": [],
                }
            ),
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            model="fixture-provider",
            metadata={"provider": "fixture"},
        )
