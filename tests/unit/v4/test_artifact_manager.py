import json
from pathlib import Path

import pytest

from homllm_v4.artifacts.manager import ArtifactManager


def test_create_run_creates_required_layout(tmp_path: Path) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")

    manager.create_run("run-1", {"purpose": "test"})

    run_dir = tmp_path / ".homllm" / "runs" / "run-1"
    assert (run_dir / "metadata.json").is_file()
    assert (run_dir / "task.json").is_file()
    assert (run_dir / "events.jsonl").is_file()
    for name in ("snapshots", "evidence", "context", "commands", "patches", "verification", "response"):
        assert (run_dir / name).is_dir()
    assert json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))["purpose"] == "test"


def test_write_json_returns_artifact_ref_with_stable_hash(tmp_path: Path) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("run-1", {})

    first = manager.write_json("evidence/candidates.json", {"b": 2, "a": 1}, "evidence", "candidate dump")
    second = manager.write_json("evidence/candidates-copy.json", {"b": 2, "a": 1}, "evidence", "candidate dump")

    assert first.artifact_type == "evidence"
    assert first.description == "candidate dump"
    assert first.content_hash == second.content_hash
    assert first.path.endswith(".homllm/runs/run-1/evidence/candidates.json")


def test_write_text_returns_artifact_ref(tmp_path: Path) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("run-1", {})

    artifact = manager.write_text("context/context.txt", "hello", "context", "context text")

    assert artifact.content_hash is not None
    assert (tmp_path / artifact.path).read_text(encoding="utf-8") == "hello"


def test_path_traversal_is_denied(tmp_path: Path) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("run-1", {})

    with pytest.raises(ValueError, match="path_denied"):
        manager.write_text("../escape.txt", "bad", "debug", "bad")
