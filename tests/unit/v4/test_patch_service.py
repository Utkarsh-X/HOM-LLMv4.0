import hashlib
from pathlib import Path

from homllm_v4.contracts.patch import FilePatch, PatchApplyRequest, PatchRollbackRequest
from homllm_v4.services.patch_service import WorkspacePatchService


def content_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def test_patch_service_applies_workspace_scoped_file_patch(tmp_path: Path) -> None:
    target = tmp_path / "src" / "demo.py"
    target.parent.mkdir()
    original = "def value():\n    return 1\n"
    target.write_text(original, encoding="utf-8")
    service = WorkspacePatchService()

    result = service.apply(
        PatchApplyRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            patches=(
                FilePatch(
                    file_path="src/demo.py",
                    expected_content_hash=content_hash(original),
                    new_content="def value():\n    return 2\n",
                ),
            ),
            dry_run=False,
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.applied is True
    assert target.read_text(encoding="utf-8") == "def value():\n    return 2\n"
    assert "-    return 1" in result.output.file_results[0].diff
    assert "+    return 2" in result.output.file_results[0].diff


def test_patch_service_dry_run_does_not_write(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    original = "x = 1\n"
    target.write_text(original, encoding="utf-8")
    service = WorkspacePatchService()

    result = service.apply(
        PatchApplyRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            patches=(
                FilePatch(
                    file_path="demo.py",
                    expected_content_hash=content_hash(original),
                    new_content="x = 2\n",
                ),
            ),
            dry_run=True,
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.applied is False
    assert target.read_text(encoding="utf-8") == original


def test_patch_service_denies_path_escape(tmp_path: Path) -> None:
    service = WorkspacePatchService()

    result = service.apply(
        PatchApplyRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            patches=(
                FilePatch(
                    file_path="../escape.py",
                    expected_content_hash=None,
                    new_content="bad\n",
                ),
            ),
            dry_run=False,
        )
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "path_denied"


def test_patch_service_blocks_stale_context(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    target.write_text("x = 2\n", encoding="utf-8")
    service = WorkspacePatchService()

    result = service.apply(
        PatchApplyRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            patches=(
                FilePatch(
                    file_path="demo.py",
                    expected_content_hash=content_hash("x = 1\n"),
                    new_content="x = 3\n",
                ),
            ),
            dry_run=False,
        )
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "stale_context"
    assert target.read_text(encoding="utf-8") == "x = 2\n"


def test_patch_service_blocks_unexpected_file_change(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed.py"
    unexpected = tmp_path / "unexpected.py"
    allowed.write_text("x = 1\n", encoding="utf-8")
    unexpected.write_text("y = 1\n", encoding="utf-8")
    service = WorkspacePatchService()

    result = service.apply(
        PatchApplyRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            patches=(
                FilePatch(
                    file_path="unexpected.py",
                    expected_content_hash=content_hash("y = 1\n"),
                    new_content="y = 2\n",
                ),
            ),
            allowed_file_paths=("allowed.py",),
        )
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "diff_inspection_failed"
    assert unexpected.read_text(encoding="utf-8") == "y = 1\n"


def test_patch_service_blocks_too_many_file_changes(tmp_path: Path) -> None:
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text("x = 1\n", encoding="utf-8")
    second.write_text("y = 1\n", encoding="utf-8")
    service = WorkspacePatchService()

    result = service.apply(
        PatchApplyRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            patches=(
                FilePatch("first.py", content_hash("x = 1\n"), "x = 2\n"),
                FilePatch("second.py", content_hash("y = 1\n"), "y = 2\n"),
            ),
            max_file_changes=1,
        )
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "diff_inspection_failed"
    assert first.read_text(encoding="utf-8") == "x = 1\n"
    assert second.read_text(encoding="utf-8") == "y = 1\n"


def test_patch_service_rolls_back_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "demo.py"
    original = "x = 1\n"
    target.write_text(original, encoding="utf-8")
    service = WorkspacePatchService()
    apply_result = service.apply(
        PatchApplyRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            patches=(FilePatch("demo.py", content_hash(original), "x = 2\n"),),
        )
    )
    assert apply_result.ok is True
    assert apply_result.output is not None
    assert target.read_text(encoding="utf-8") == "x = 2\n"

    rollback = service.rollback(
        PatchRollbackRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            file_results=apply_result.output.file_results,
        )
    )

    assert rollback.ok is True
    assert rollback.output is not None
    assert rollback.output.rolled_back is True
    assert rollback.output.restored_files == ("demo.py",)
    assert target.read_text(encoding="utf-8") == original


def test_patch_service_rolls_back_newly_created_file(tmp_path: Path) -> None:
    target = tmp_path / "new.py"
    service = WorkspacePatchService()
    apply_result = service.apply(
        PatchApplyRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            patches=(FilePatch("new.py", None, "created = True\n"),),
        )
    )
    assert apply_result.ok is True
    assert apply_result.output is not None
    assert target.exists()

    rollback = service.rollback(
        PatchRollbackRequest(
            task_id="task-1",
            workspace_root=str(tmp_path),
            file_results=apply_result.output.file_results,
        )
    )

    assert rollback.ok is True
    assert rollback.output is not None
    assert rollback.output.deleted_files == ("new.py",)
    assert not target.exists()
