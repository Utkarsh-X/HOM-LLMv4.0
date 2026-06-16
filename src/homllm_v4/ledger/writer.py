import json
from pathlib import Path

from homllm_v4.ledger.events import RunEvent
from homllm_v4.serialization.json import to_jsonable


class EventWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: RunEvent) -> None:
        try:
            payload = json.dumps(to_jsonable(event), sort_keys=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(payload + "\n")
                handle.flush()
        except Exception as exc:
            raise ValueError("event_write_failed") from exc
