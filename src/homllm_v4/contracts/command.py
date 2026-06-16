from dataclasses import dataclass


@dataclass(frozen=True)
class CommandPolicy:
    allowed_executables: tuple[str, ...]
    default_timeout_seconds: int
    max_timeout_seconds: int
    approval_required_executables: tuple[str, ...] = ()
    allowed_env_vars: tuple[str, ...] = (
        "PATH",
        "PATHEXT",
        "SystemRoot",
        "COMSPEC",
        "TEMP",
        "TMP",
        "PYTHONPATH",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
    )


@dataclass(frozen=True)
class CommandRunRequest:
    task_id: str
    workspace_root: str
    cwd: str
    argv: tuple[str, ...]
    timeout_seconds: int | None = None


@dataclass(frozen=True)
class CommandRunResult:
    argv: tuple[str, ...]
    cwd: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    denied: bool
