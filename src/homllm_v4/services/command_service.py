import os
import subprocess
from pathlib import Path
from time import perf_counter

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.command import CommandPolicy, CommandRunRequest, CommandRunResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.services.approval_service import ApprovalRegistry


class LocalCommandService:
    def __init__(
        self,
        *,
        policy: CommandPolicy,
        approval_registry: ApprovalRegistry | None = None,
        session_id: str = "default",
    ) -> None:
        self.policy = policy
        self.approval_registry = approval_registry
        self.session_id = session_id

    def run(self, request: CommandRunRequest) -> CapabilityResult[CommandRunResult]:
        started = perf_counter()
        if not request.argv:
            return self._failed(request, started, "command_denied", "empty argv")

        executable = Path(request.argv[0]).name
        if executable in self.policy.approval_required_executables:
            if not self._is_approved(request, executable):
                return self._failed(
                    request,
                    started,
                    "requires_approval",
                    f"command execution requires approval: {executable}",
                    details={
                        "approval_scope": "command_execution",
                        "executable": executable,
                    },
                )
        elif executable not in self.policy.allowed_executables:
            return self._failed(
                request,
                started,
                "command_denied",
                f"executable not allowlisted: {executable}",
            )

        workspace_root = Path(request.workspace_root).resolve()
        cwd = (workspace_root / request.cwd).resolve()
        try:
            cwd.relative_to(workspace_root)
        except ValueError:
            return self._failed(request, started, "path_denied", f"cwd escapes workspace: {cwd}")

        timeout = self._timeout(request.timeout_seconds)
        try:
            completed = subprocess.run(
                list(request.argv),
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._environment(),
                shell=False,
                check=False,
            )
            output = CommandRunResult(
                argv=request.argv,
                cwd=str(cwd),
                exit_code=int(completed.returncode),
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration_ms=self._duration_ms(started),
                timed_out=False,
                denied=False,
            )
        except subprocess.TimeoutExpired as exc:
            output = CommandRunResult(
                argv=request.argv,
                cwd=str(cwd),
                exit_code=None,
                stdout=self._decode_timeout_stream(exc.stdout),
                stderr=self._decode_timeout_stream(exc.stderr),
                duration_ms=self._duration_ms(started),
                timed_out=True,
                denied=False,
            )

        return CapabilityResult(
            capability_name="command.run",
            ok=True,
            output=output,
            error=None,
            telemetry=self._telemetry(
                request,
                started,
                {"exit_code": output.exit_code, "timed_out": output.timed_out},
            ),
            artifacts=(),
        )

    def _failed(
        self,
        request: CommandRunRequest,
        started: float,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> CapabilityResult[CommandRunResult]:
        return CapabilityResult(
            capability_name="command.run",
            ok=False,
            output=None,
            error=CapabilityError(
                code=code,
                message=message,
                recoverable=True,
                retryable=False,
                details={"argv": request.argv, "cwd": request.cwd, **(details or {})},
            ),
            telemetry=self._telemetry(request, started, {"denied": True, "code": code}),
            artifacts=(),
        )

    def _timeout(self, requested: int | None) -> int:
        timeout = requested if requested is not None else self.policy.default_timeout_seconds
        timeout = max(1, int(timeout))
        return min(timeout, max(1, int(self.policy.max_timeout_seconds)))

    def _is_approved(self, request: CommandRunRequest, executable: str) -> bool:
        if self.approval_registry is None:
            return False
        return self.approval_registry.is_approved(
            task_id=request.task_id,
            session_id=self.session_id,
            requested_capability="command_execution",
            subject=executable,
        )

    def _environment(self) -> dict[str, str]:
        return {
            name: os.environ[name]
            for name in self.policy.allowed_env_vars
            if name in os.environ
        }

    @staticmethod
    def _decode_timeout_stream(value: bytes | str | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    @staticmethod
    def _duration_ms(started: float) -> int:
        return int((perf_counter() - started) * 1000)

    def _telemetry(
        self,
        request: CommandRunRequest,
        started: float,
        output_summary: dict[str, object],
    ) -> CapabilityTelemetry:
        return CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=self._duration_ms(started),
            input_summary={"task_id": request.task_id, "argv": request.argv, "cwd": request.cwd},
            output_summary=output_summary,
            token_usage={},
            model_usage={},
            degraded=False,
            degradation_reason=None,
        )
