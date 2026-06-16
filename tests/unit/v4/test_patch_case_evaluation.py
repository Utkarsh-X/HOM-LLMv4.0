import hashlib
import shutil
import sys
from pathlib import Path

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.command import CommandPolicy
from homllm_v4.contracts.evaluation import EvaluationCase
from homllm_v4.evaluation.harness import V4EvaluationHarness
from homllm_v4.evaluation.patch_cases import build_write_verify_request_from_case
from homllm_v4.evaluation.fixture_suites import run_python_provider_patch_fixture_suite
from homllm_v4.evaluation.runners import make_write_verify_runner
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.runtime.write_verify_loop import WriteVerifyLoop
from homllm_v4.services.command_service import LocalCommandService
from homllm_v4.services.patch_service import WorkspacePatchService


def content_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def copy_fixture_repo(tmp_path: Path, name: str = "repo") -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    source = repo_root / "fixtures" / "v4" / "python_patch_repo"
    target = tmp_path / name
    shutil.copytree(source, target)
    return target


def test_build_write_verify_request_from_patch_case_payload(tmp_path: Path) -> None:
    workspace = copy_fixture_repo(tmp_path)
    original = (workspace / "calculator.py").read_text(encoding="utf-8")
    fixed = original.replace("return a - b", "return a + b")
    case = EvaluationCase(
        case_id="py-add-fix",
        runner_id="write_verify",
        task_type="python_patch",
        input_payload={
            "file_path": "calculator.py",
            "expected_content_hash": content_hash(original),
            "new_content": fixed,
            "allowed_file_paths": ("calculator.py",),
            "verification_argv": (sys.executable, "-m", "pytest", ".", "-q"),
        },
        expected_stop_reason="verified",
    )

    request = build_write_verify_request_from_case(case, workspace_root=workspace, run_id="run-1")

    assert request.task_id == "py-add-fix"
    assert request.run_id == "run-1"
    assert request.workspace_root == str(workspace)
    assert request.patch_request.allowed_file_paths == ("calculator.py",)
    assert request.patch_request.max_file_changes == 1
    assert request.patch_request.patches[0].file_path == "calculator.py"
    assert request.patch_request.patches[0].new_content == fixed
    assert request.verification_commands[0].cwd == "."
    assert request.verification_commands[0].argv == (sys.executable, "-m", "pytest", ".", "-q")


def test_fixture_patch_case_runs_through_evaluation_harness(tmp_path: Path) -> None:
    workspace = copy_fixture_repo(tmp_path)
    original = (workspace / "calculator.py").read_text(encoding="utf-8")
    fixed = original.replace("return a - b", "return a + b")
    run_id = "fixture-patch-run"
    case = EvaluationCase(
        case_id="py-add-fix",
        runner_id="write_verify",
        task_type="python_patch",
        input_payload={
            "file_path": "calculator.py",
            "expected_content_hash": content_hash(original),
            "new_content": fixed,
            "allowed_file_paths": ("calculator.py",),
            "verification_argv": (sys.executable, "-m", "pytest", ".", "-q"),
        },
        expected_stop_reason="verified",
    )
    artifact_manager = ArtifactManager(
        workspace_root=workspace,
        artifact_root=workspace / ".homllm" / "runs",
    )
    artifact_manager.create_run(run_id, {"case_id": case.case_id})
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
        event_writer=EventWriter(workspace / ".homllm" / "runs" / run_id / "events.jsonl"),
    )
    runner = make_write_verify_runner(
        loop,
        lambda evaluation_case: build_write_verify_request_from_case(
            evaluation_case,
            workspace_root=workspace,
            run_id=run_id,
        ),
    )
    harness = V4EvaluationHarness(
        artifact_manager=artifact_manager,
        runners={"write_verify": runner},
    )

    result = harness.run(run_id=run_id, cases=(case,))

    assert result.total_cases == 1
    assert result.passed_cases == 1
    assert result.failed_cases == 0
    assert "return a + b" in (workspace / "calculator.py").read_text(encoding="utf-8")
    assert (workspace / ".homllm" / "runs" / run_id / "evaluation" / "summary.json").is_file()


def test_fixture_patch_safety_suite_runs_through_evaluation_harness(tmp_path: Path) -> None:
    fixture = copy_fixture_repo(tmp_path, "fixture-source")
    original = (fixture / "calculator.py").read_text(encoding="utf-8")
    fixed = original.replace("return a - b", "return a + b")
    wrong_but_valid = original.replace("return a - b", "return a * b")
    run_id = "fixture-safety-suite"
    workspaces: dict[str, Path] = {}

    cases = (
        EvaluationCase(
            case_id="verified-fix",
            runner_id="write_verify",
            task_type="python_patch",
            input_payload={
                "file_path": "calculator.py",
                "expected_content_hash": content_hash(original),
                "new_content": fixed,
                "allowed_file_paths": ("calculator.py",),
                "verification_argv": (sys.executable, "-m", "pytest", ".", "-q"),
            },
            expected_stop_reason="verified",
        ),
        EvaluationCase(
            case_id="stale-context",
            runner_id="write_verify",
            task_type="python_patch",
            input_payload={
                "file_path": "calculator.py",
                "expected_content_hash": content_hash(fixed),
                "new_content": fixed,
                "allowed_file_paths": ("calculator.py",),
                "verification_argv": (sys.executable, "-m", "pytest", ".", "-q"),
            },
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
        EvaluationCase(
            case_id="repair-budget",
            runner_id="write_verify",
            task_type="python_patch",
            input_payload={
                "file_path": "calculator.py",
                "expected_content_hash": content_hash(original),
                "new_content": wrong_but_valid,
                "allowed_file_paths": ("calculator.py",),
                "verification_argv": (sys.executable, "-m", "pytest", ".", "-q"),
                "max_patch_attempts": 2,
            },
            expected_stop_reason="repair_budget_exhausted",
        ),
    )
    artifact_workspace = tmp_path / "artifact-workspace"
    artifact_workspace.mkdir()
    artifact_manager = ArtifactManager(
        workspace_root=artifact_workspace,
        artifact_root=artifact_workspace / ".homllm" / "runs",
    )
    artifact_manager.create_run(run_id, {"case_count": len(cases)})
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
        event_writer=EventWriter(artifact_workspace / ".homllm" / "runs" / run_id / "events.jsonl"),
    )

    def build_request(case: EvaluationCase):
        workspace = copy_fixture_repo(tmp_path, case.case_id)
        workspaces[case.case_id] = workspace
        return build_write_verify_request_from_case(case, workspace_root=workspace, run_id=run_id)

    harness = V4EvaluationHarness(
        artifact_manager=artifact_manager,
        runners={"write_verify": make_write_verify_runner(loop, build_request)},
    )

    result = harness.run(run_id=run_id, cases=cases)

    assert result.total_cases == 4
    assert result.passed_cases == 4
    assert result.failed_cases == 0
    assert "return a + b" in (workspaces["verified-fix"] / "calculator.py").read_text(encoding="utf-8")
    assert not (workspaces["unexpected-file"] / "side_effect.py").exists()
    assert (artifact_workspace / ".homllm" / "runs" / run_id / "evaluation" / "summary.json").is_file()


def test_provider_proposed_fixture_suite_runs_through_evaluation_harness(tmp_path: Path) -> None:
    fixture = copy_fixture_repo(tmp_path, "provider-fixture-source")

    result = run_python_provider_patch_fixture_suite(
        fixture_root=fixture,
        workspace_root=tmp_path / "provider-work",
        artifact_root=tmp_path / "provider-runs",
        run_id="provider-suite",
    )

    assert result.total_cases == 2
    assert result.passed_cases == 2
    assert result.failed_cases == 0
    assert result.summary_metrics["stop_reason_counts"]["verified"] == 1
    assert result.summary_metrics["error_code_counts"]["proposal_evidence_scope_denied"] == 1
