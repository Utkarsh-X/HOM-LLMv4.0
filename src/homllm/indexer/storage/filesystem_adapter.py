"""Filesystem adapter for artifact storage."""

import json
from pathlib import Path
from typing import Any

from homllm.indexer.interfaces import StorageAdapter


class FilesystemAdapter(StorageAdapter):
    """Filesystem-based storage adapter for immutable artifacts."""

    def __init__(self, base_path: Path):
        """
        Initialize filesystem adapter.
        
        Artifacts stored:
        - symbols.json
        - files.json
        - callgraph.json
        - dependencies.json
        """
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def read(self, key: str) -> bytes:
        """Read data by key."""
        file_path = self.base_path / key
        if not file_path.exists():
            raise FileNotFoundError(f"Artifact not found: {key}")
        return file_path.read_bytes()

    def write(self, key: str, data: bytes) -> None:
        """Write data by key."""
        file_path = self.base_path / key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(data)

    def exists(self, key: str) -> bool:
        """Check if key exists."""
        return (self.base_path / key).exists()

    def delete(self, key: str) -> None:
        """Delete data by key."""
        file_path = self.base_path / key
        if file_path.exists():
            file_path.unlink()

    def write_json(self, key: str, data: Any) -> None:
        """Write JSON data (convenience method)."""
        json_str = json.dumps(data, indent=2, sort_keys=True)
        self.write(key, json_str.encode("utf-8"))

    def read_json(self, key: str) -> Any:
        """Read JSON data (convenience method)."""
        data = self.read(key)
        return json.loads(data.decode("utf-8"))
