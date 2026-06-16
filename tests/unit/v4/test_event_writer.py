import json
from pathlib import Path

import pytest

from homllm_v4.contracts.artifacts import ArtifactRef
from homllm_v4.ledger.events import RunEvent
from homllm_v4.ledger.writer import EventWriter


def event(event_type: str, artifact_refs: tuple[ArtifactRef, ...] = ()) -> RunEvent:
    return RunEvent(
        event_id=f"event-{event_type}",
        run_id="run-1",
        task_id="task-1",
        phase="test",
        event_type=event_type,
        timestamp="2026-05-09T00:00:00Z",
        summary={"ok": True},
        artifact_refs=artifact_refs,
    )


def test_event_writer_appends_json_lines_in_order(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    writer = EventWriter(path)

    writer.append(event("run_started"))
    writer.append(event("run_completed"))

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event_type"] == "run_started"
    assert json.loads(lines[1])["event_type"] == "run_completed"


def test_event_writer_serializes_artifact_refs(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    writer = EventWriter(path)
    artifact = ArtifactRef("context", ".homllm/runs/run-1/context/a.json", "context", "abc")

    writer.append(event("context_completed", (artifact,)))

    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert payload["artifact_refs"][0]["artifact_type"] == "context"
    assert payload["artifact_refs"][0]["content_hash"] == "abc"


def test_event_writer_wraps_serialization_failures(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    writer = EventWriter(path)
    bad_event = event("run_failed")
    bad_event.summary["unsupported"] = object()

    with pytest.raises(ValueError, match="event_write_failed") as exc_info:
        writer.append(bad_event)

    assert exc_info.value.__cause__ is not None
