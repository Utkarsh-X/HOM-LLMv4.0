from pathlib import Path

from homllm_v4.contracts.evidence import DirectReadRequest
from homllm_v4.services.direct_read_service import DirectReadService


def test_reads_workspace_file_with_hash(tmp_path: Path) -> None:
    target = tmp_path / "src" / "demo.py"
    target.parent.mkdir()
    target.write_text("line1\nline2\nline3\n", encoding="utf-8")
    service = DirectReadService(workspace_root=tmp_path)

    result = service.read(DirectReadRequest(task_id="task-1", file_path="src/demo.py"))

    assert result.ok is True
    assert result.output is not None
    assert result.output.content_excerpt == "line1\nline2\nline3\n"
    assert result.output.content_hash is not None
    assert result.output.freshness == "fresh"


def test_line_slicing_is_one_based_and_inclusive(tmp_path: Path) -> None:
    target = tmp_path / "src" / "demo.py"
    target.parent.mkdir()
    target.write_text("line1\nline2\nline3\n", encoding="utf-8")
    service = DirectReadService(workspace_root=tmp_path)

    result = service.read(
        DirectReadRequest(
            task_id="task-1",
            file_path="src/demo.py",
            line_start=2,
            line_end=3,
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.content_excerpt == "line2\nline3\n"


def test_path_outside_workspace_is_denied(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    service = DirectReadService(workspace_root=tmp_path)

    result = service.read(DirectReadRequest(task_id="task-1", file_path="../outside.txt"))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "path_denied"


def test_large_file_limit_is_enforced(tmp_path: Path) -> None:
    target = tmp_path / "large.txt"
    target.write_text("abcdef", encoding="utf-8")
    service = DirectReadService(workspace_root=tmp_path)

    result = service.read(DirectReadRequest(task_id="task-1", file_path="large.txt", max_bytes=3))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "file_too_large"


def test_missing_file_returns_structured_error(tmp_path: Path) -> None:
    service = DirectReadService(workspace_root=tmp_path)

    result = service.read(DirectReadRequest(task_id="task-1", file_path="missing.py"))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "file_not_found"


def test_non_utf8_file_is_denied(tmp_path: Path) -> None:
    target = tmp_path / "binary.dat"
    target.write_bytes(b"\xff\xfe\x00\x00")
    service = DirectReadService(workspace_root=tmp_path)

    result = service.read(DirectReadRequest(task_id="task-1", file_path="binary.dat"))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "binary_file_denied"
