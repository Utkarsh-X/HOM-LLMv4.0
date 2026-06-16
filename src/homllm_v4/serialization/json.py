import json
from dataclasses import asdict, is_dataclass
from pathlib import Path


def to_jsonable(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise ValueError(f"serialization_failed: unsupported dict key {type(key).__name__}")
        return {key: to_jsonable(item) for key, item in value.items()}
    raise ValueError(f"serialization_failed: unsupported type {type(value).__name__}")


def write_json_file(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_jsonable(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json_file(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("serialization_failed: expected JSON object")
    return data
