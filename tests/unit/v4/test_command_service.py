import sys
from pathlib import Path

from homllm_v4.contracts.approval import ApprovalDecision, ApprovalRequest
from homllm_v4.contracts.command import CommandPolicy, CommandRunRequest
from homllm_v4.services.approval_service import ApprovalRegistry
from homllm_v4.services.command_service import LocalCommandService


def test_command_service_runs_allowlisted_structured_argv(tmp_path: Path) -> None:
    service = LocalCommandService(
        policy=CommandPolicy(
            allowed_executables=(Path(sys.executable).name,),
            default_timeout_seconds=5,
            max_timeout_seconds=10,
        )
    )

    result = service.run(
        CommandRunRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            cwd=".",
            argv=(sys.executable, "-c", "print('verified')"),
            timeout_seconds=5,
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.exit_code == 0
    assert result.output.stdout.strip() == "verified"
    assert result.output.timed_out is False
    assert result.output.denied is False


def test_command_service_denies_unallowlisted_executable(tmp_path: Path) -> None:
    service = LocalCommandService(
        policy=CommandPolicy(
            allowed_executables=("pytest",),
            default_timeout_seconds=5,
            max_timeout_seconds=10,
        )
    )

    result = service.run(
        CommandRunRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            cwd=".",
            argv=(sys.executable, "-c", "print('blocked')"),
            timeout_seconds=5,
        )
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "command_denied"


def test_command_service_returns_requires_approval_for_approval_gated_executable(
    tmp_path: Path,
) -> None:
    service = LocalCommandService(
        policy=CommandPolicy(
            allowed_executables=(),
            approval_required_executables=(Path(sys.executable).name,),
            default_timeout_seconds=5,
            max_timeout_seconds=10,
        )
    )

    result = service.run(
        CommandRunRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            cwd=".",
            argv=(sys.executable, "-c", "print('needs approval')"),
            timeout_seconds=5,
        )
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "requires_approval"
    assert result.error.details["approval_scope"] == "command_execution"
    assert result.error.details["executable"] == Path(sys.executable).name


def test_command_service_runs_approval_gated_executable_after_session_approval(
    tmp_path: Path,
) -> None:
    registry = ApprovalRegistry()
    registry.record(
        ApprovalRequest(
            request_id="approval-1",
            task_id="task-1",
            session_id="session-1",
            requested_capability="command_execution",
            subject=Path(sys.executable).name,
            reason="run verification",
        ),
        ApprovalDecision(
            request_id="approval-1",
            approved=True,
            scope="session",
            approver="test",
        ),
    )
    service = LocalCommandService(
        policy=CommandPolicy(
            allowed_executables=(),
            approval_required_executables=(Path(sys.executable).name,),
            default_timeout_seconds=5,
            max_timeout_seconds=10,
        ),
        approval_registry=registry,
        session_id="session-1",
    )

    result = service.run(
        CommandRunRequest(
            task_id="task-2",
            workspace_root=str(tmp_path),
            cwd=".",
            argv=(sys.executable, "-c", "print('approved')"),
            timeout_seconds=5,
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.exit_code == 0
    assert result.output.stdout.strip() == "approved"


def test_command_service_denies_cwd_escape(tmp_path: Path) -> None:
    service = LocalCommandService(
        policy=CommandPolicy(
            allowed_executables=(Path(sys.executable).name,),
            default_timeout_seconds=5,
            max_timeout_seconds=10,
        )
    )

    result = service.run(
        CommandRunRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            cwd="..",
            argv=(sys.executable, "-c", "print('blocked')"),
            timeout_seconds=5,
        )
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "path_denied"


def test_command_service_reports_timeout(tmp_path: Path) -> None:
    service = LocalCommandService(
        policy=CommandPolicy(
            allowed_executables=(Path(sys.executable).name,),
            default_timeout_seconds=1,
            max_timeout_seconds=1,
        )
    )

    result = service.run(
        CommandRunRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            cwd=".",
            argv=(sys.executable, "-c", "import time; time.sleep(2)"),
            timeout_seconds=1,
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.timed_out is True
    assert result.output.exit_code is None


def test_command_service_filters_unlisted_environment_variables(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HOMLLM_SHOULD_NOT_LEAK", "secret")
    service = LocalCommandService(
        policy=CommandPolicy(
            allowed_executables=(Path(sys.executable).name,),
            default_timeout_seconds=5,
            max_timeout_seconds=10,
        )
    )

    result = service.run(
        CommandRunRequest(
            task_id="task-env-filter",
            workspace_root=str(tmp_path),
            cwd=".",
            argv=(
                sys.executable,
                "-c",
                "import os; raise SystemExit(1 if os.environ.get('HOMLLM_SHOULD_NOT_LEAK') else 0)",
            ),
            timeout_seconds=5,
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.exit_code == 0


def test_command_service_allows_explicit_environment_variables(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HOMLLM_ALLOWED_ENV", "visible")
    service = LocalCommandService(
        policy=CommandPolicy(
            allowed_executables=(Path(sys.executable).name,),
            default_timeout_seconds=5,
            max_timeout_seconds=10,
            allowed_env_vars=("HOMLLM_ALLOWED_ENV",),
        )
    )

    result = service.run(
        CommandRunRequest(
            task_id="task-env-allow",
            workspace_root=str(tmp_path),
            cwd=".",
            argv=(
                sys.executable,
                "-c",
                "import os; raise SystemExit(0 if os.environ.get('HOMLLM_ALLOWED_ENV') == 'visible' else 1)",
            ),
            timeout_seconds=5,
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.exit_code == 0
