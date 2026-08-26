import hashlib
import json
import sys
from pathlib import Path

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.command import CommandPolicy, CommandRunRequest
from homllm_v4.contracts.patch import FilePatch, PatchApplyRequest
from homllm_v4.contracts.write_loop import WriteVerifyLoopRequest
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.runtime.write_verify_loop import WriteVerifyLoop
from homllm_v4.services.command_service import LocalCommandService
from homllm_v4.services.patch_service import WorkspacePatchService


def content_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def loop(tmp_path: Path) -> WriteVerifyLoop:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("run-1", {})
    return WriteVerifyLoop(
        patch_service=WorkspacePatchService(),
        command_service=LocalCommandService(
            policy=CommandPolicy(
                allowed_executables=(Path(sys.executable).name,),
                default_timeout_seconds=5,
                max_timeout_seconds=5,
            )
        ),
        artifact_manager=manager,
        event_writer=EventWriter(tmp_path / ".homllm" / "runs" / "run-1" / "events.jsonl"),
    )


def request(
    tmp_path: Path,
    patch: PatchApplyRequest,
    commands: tuple[CommandRunRequest, ...],
    max_verification_commands: int = 3,
    repair_patch_requests: tuple[PatchApplyRequest, ...] = (),
    max_patch_attempts: int = 1,
    rollback_on_failure: bool = False,
) -> WriteVerifyLoopRequest:
    return WriteVerifyLoopRequest(
        task_id="task-1",
        run_id="run-1",
        workspace_root=str(tmp_path),
        patch_request=patch,
        verification_commands=commands,
        max_verification_commands=max_verification_commands,
        repair_patch_requests=repair_patch_requests,
        max_patch_attempts=max_patch_attempts,
        rollback_on_failure=rollback_on_failure,
    )


def test_write_verify_loop_stops_verified_and_persists_result(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    original = "VALUE = 1\n"
    target.write_text(original, encoding="utf-8")
    patch = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash(original), "VALUE = 2\n"),),
    )
    command = CommandRunRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        cwd=".",
        argv=(sys.executable, "-c", "import demo; raise SystemExit(0 if demo.VALUE == 2 else 1)"),
        timeout_seconds=5,
    )

    result = loop(tmp_path).run(request(tmp_path, patch, (command,)))

    assert result.stop_reason == "verified"
    assert result.patch_result is not None
    assert result.patch_result.applied is True
    assert len(result.verification_results) == 1
    assert result.verification_results[0].exit_code == 0
    assert "verified" in result.response_text
    artifact = tmp_path / ".homllm" / "runs" / "run-1" / "response" / "write_verify_loop_result.json"
    assert artifact.is_file()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["stop_reason"] == "verified"


def test_write_verify_loop_stops_on_patch_failure(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    target.write_text("VALUE = 2\n", encoding="utf-8")
    patch = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash("VALUE = 1\n"), "VALUE = 3\n"),),
    )

    result = loop(tmp_path).run(request(tmp_path, patch, ()))

    assert result.stop_reason == "patch_failed"
    assert result.error is not None
    assert result.error.code == "stale_context"
    assert result.verification_results == ()


def test_write_verify_loop_stops_on_verification_failure(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    original = "VALUE = 1\n"
    target.write_text(original, encoding="utf-8")
    patch = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash(original), "VALUE = 2\n"),),
    )
    command = CommandRunRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        cwd=".",
        argv=(sys.executable, "-c", "raise SystemExit(3)"),
        timeout_seconds=5,
    )

    result = loop(tmp_path).run(request(tmp_path, patch, (command,)))

    assert result.stop_reason == "verification_failed"
    assert result.error is None
    assert result.verification_results[0].exit_code == 3
    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"


def test_write_verify_loop_blocks_unexpected_verification_file_side_effect(
    tmp_path: Path,
) -> None:
    target = tmp_path / "demo.py"
    original = "VALUE = 1\n"
    target.write_text(original, encoding="utf-8")
    patch = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash(original), "VALUE = 2\n"),),
    )
    command = CommandRunRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        cwd=".",
        argv=(
            sys.executable,
            "-c",
            "from pathlib import Path; Path('side_effect.txt').write_text('bad'); raise SystemExit(0)",
        ),
        timeout_seconds=5,
    )

    result = loop(tmp_path).run(request(tmp_path, patch, (command,)))

    assert result.stop_reason == "verification_side_effect"
    assert result.error is not None
    assert result.error.code == "verification_side_effect"
    assert result.error.details["changed_files"] == ("side_effect.txt",)


def test_write_verify_loop_cleans_created_side_effect_when_rollback_enabled(
    tmp_path: Path,
) -> None:
    target = tmp_path / "demo.py"
    original = "VALUE = 1\n"
    target.write_text(original, encoding="utf-8")
    patch = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash(original), "VALUE = 2\n"),),
    )
    command = CommandRunRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        cwd=".",
        argv=(
            sys.executable,
            "-c",
            "from pathlib import Path; Path('side_effect.txt').write_text('bad'); raise SystemExit(0)",
        ),
        timeout_seconds=5,
    )

    result = loop(tmp_path).run(request(tmp_path, patch, (command,), rollback_on_failure=True))

    assert result.stop_reason == "verification_side_effect"
    assert not (tmp_path / "side_effect.txt").exists()
    assert result.error is not None
    assert result.error.details["cleaned_files"] == ("side_effect.txt",)


def test_write_verify_loop_restores_modified_side_effect_when_rollback_enabled(
    tmp_path: Path,
) -> None:
    target = tmp_path / "demo.py"
    original = "VALUE = 1\n"
    target.write_text(original, encoding="utf-8")
    unrelated = tmp_path / "notes.txt"
    unrelated.write_text("before\n", encoding="utf-8")
    patch = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash(original), "VALUE = 2\n"),),
    )
    command = CommandRunRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        cwd=".",
        argv=(
            sys.executable,
            "-c",
            "from pathlib import Path; Path('notes.txt').write_text('after\\n'); raise SystemExit(0)",
        ),
        timeout_seconds=5,
    )

    result = loop(tmp_path).run(request(tmp_path, patch, (command,), rollback_on_failure=True))

    assert result.stop_reason == "verification_side_effect"
    assert unrelated.read_text(encoding="utf-8") == "before\n"
    assert result.error is not None
    assert result.error.details["cleaned_files"] == ("notes.txt",)


def test_write_verify_loop_rolls_back_after_verification_failure_when_enabled(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    original = "VALUE = 1\n"
    target.write_text(original, encoding="utf-8")
    patch = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash(original), "VALUE = 2\n"),),
    )
    command = CommandRunRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        cwd=".",
        argv=(sys.executable, "-c", "raise SystemExit(3)"),
        timeout_seconds=5,
    )

    result = loop(tmp_path).run(
        request(tmp_path, patch, (command,), rollback_on_failure=True)
    )

    assert result.stop_reason == "verification_failed"
    assert result.rollback_result is not None
    assert result.rollback_result.rolled_back is True
    assert result.rollback_result.restored_files == ("demo.py",)
    assert target.read_text(encoding="utf-8") == original


def test_write_verify_loop_stops_on_verification_timeout(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    original = "VALUE = 1\n"
    target.write_text(original, encoding="utf-8")
    patch = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash(original), "VALUE = 2\n"),),
    )
    command = CommandRunRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        cwd=".",
        argv=(sys.executable, "-c", "import time; time.sleep(2)"),
        timeout_seconds=1,
    )

    result = loop(tmp_path).run(request(tmp_path, patch, (command,)))

    assert result.stop_reason == "verification_timeout"
    assert result.verification_results[0].timed_out is True


def test_write_verify_loop_stops_on_budget_exhaustion(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    original = "VALUE = 1\n"
    target.write_text(original, encoding="utf-8")
    patch = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash(original), "VALUE = 2\n"),),
    )
    command = CommandRunRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        cwd=".",
        argv=(sys.executable, "-c", "raise SystemExit(0)"),
        timeout_seconds=5,
    )

    result = loop(tmp_path).run(
        request(tmp_path, patch, (command,), max_verification_commands=0)
    )

    assert result.stop_reason == "budget_exhausted"
    assert result.verification_results == ()


def test_write_verify_loop_repairs_after_failed_verification(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    original = "VALUE = 1\n"
    target.write_text(original, encoding="utf-8")
    primary = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash(original), "VALUE = 2\n"),),
    )
    repair = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash("VALUE = 2\n"), "VALUE = 3\n"),),
    )
    command = CommandRunRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        cwd=".",
        argv=(
            sys.executable,
            "-c",
            "from pathlib import Path; raise SystemExit(0 if Path('demo.py').read_text() == 'VALUE = 3\\n' else 1)",
        ),
        timeout_seconds=5,
    )

    result = loop(tmp_path).run(
        request(
            tmp_path,
            primary,
            (command,),
            repair_patch_requests=(repair,),
            max_patch_attempts=2,
        )
    )

    assert result.stop_reason == "verified"
    assert result.patch_attempt_count == 2
    assert target.read_text(encoding="utf-8") == "VALUE = 3\n"


def test_write_verify_loop_stops_when_repair_budget_exhausted(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    original = "VALUE = 1\n"
    target.write_text(original, encoding="utf-8")
    primary = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash(original), "VALUE = 2\n"),),
    )
    command = CommandRunRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        cwd=".",
        argv=(
            sys.executable,
            "-c",
            "from pathlib import Path; raise SystemExit(0 if Path('demo.py').read_text() == 'VALUE = 3\\n' else 1)",
        ),
        timeout_seconds=5,
    )

    result = loop(tmp_path).run(
        request(tmp_path, primary, (command,), max_patch_attempts=2)
    )

    assert result.stop_reason == "repair_budget_exhausted"
    assert result.patch_attempt_count == 1
    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"


def test_write_verify_loop_ignores_dependency_dir_side_effects(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    original = "VALUE = 1\n"
    target.write_text(original, encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "cfg.json").write_text("{}", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("1", encoding="utf-8")
    patch = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash(original), "VALUE = 2\n"),),
    )
    command = CommandRunRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        cwd=".",
        argv=(
            sys.executable,
            "-c",
            "from pathlib import Path; Path('.venv/cfg.json').write_text('{\"a\": 1}'); raise SystemExit(0)",
        ),
        timeout_seconds=5,
    )

    result = loop(tmp_path).run(request(tmp_path, patch, (command,), rollback_on_failure=True))

    assert result.stop_reason == "verified"
    assert result.error is None


def test_side_effect_detection_reads_only_candidate_files(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "demo.py"
    original = "VALUE = 1\n"
    target.write_text(original, encoding="utf-8")
    (tmp_path / "big.bin").write_bytes(b"x" * 8192)

    real_read_bytes = Path.read_bytes
    read_names: list[str] = []

    def counting_read_bytes(self: Path) -> bytes:
        data = real_read_bytes(self)
        read_names.append(self.name)
        return data

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)

    patch = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash(original), "VALUE = 2\n"),),
    )
    command = CommandRunRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        cwd=".",
        argv=(
            sys.executable,
            "-c",
            "from pathlib import Path; Path('stray.txt').write_text('bad'); raise SystemExit(0)",
        ),
        timeout_seconds=5,
    )

    result = loop(tmp_path).run(request(tmp_path, patch, (command,), rollback_on_failure=True))

    assert result.stop_reason == "verification_side_effect"
    assert result.error is not None
    assert result.error.details["changed_files"] == ("stray.txt",)
    assert read_names.count("big.bin") == 1


def test_write_verify_loop_stops_when_repair_patch_is_stale(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    original = "VALUE = 1\n"
    target.write_text(original, encoding="utf-8")
    primary = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash(original), "VALUE = 2\n"),),
    )
    stale_repair = PatchApplyRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        patches=(FilePatch("demo.py", content_hash("VALUE = 999\n"), "VALUE = 3\n"),),
    )
    command = CommandRunRequest(
        task_id="task-1",
        workspace_root=str(tmp_path),
        cwd=".",
        argv=(sys.executable, "-c", "raise SystemExit(1)"),
        timeout_seconds=5,
    )

    result = loop(tmp_path).run(
        request(
            tmp_path,
            primary,
            (command,),
            repair_patch_requests=(stale_repair,),
            max_patch_attempts=2,
        )
    )

    assert result.stop_reason == "patch_failed"
    assert result.error is not None
    assert result.error.code == "stale_context"
    assert result.patch_attempt_count == 2
