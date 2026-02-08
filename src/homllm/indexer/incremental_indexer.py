"""Incremental indexing change detection using file content hashes."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from homllm.common.types import FileInfo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IncrementalDiff:
    """Represents file-level change detection results."""

    changed_files: list[FileInfo]
    unchanged_files: list[FileInfo]
    deleted_paths: list[str]
    new_paths: list[str]

    @property
    def changed_paths(self) -> list[str]:
        """Normalized paths for changed/new files."""
        return [str(file_info.path).replace("\\", "/") for file_info in self.changed_files]

    @property
    def has_changes(self) -> bool:
        """True when there is at least one changed/new/deleted file."""
        return bool(self.changed_files or self.deleted_paths)


class IncrementalIndexer:
    """Maintains content-hash cache for incremental indexing."""

    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self._cached_hashes = self._load_cache()

    def diff(self, files: list[FileInfo]) -> IncrementalDiff:
        """Compute changed/unchanged/deleted files against cache."""
        changed_files: list[FileInfo] = []
        unchanged_files: list[FileInfo] = []
        new_paths: list[str] = []

        current_hashes: dict[str, str] = {}

        for file_info in files:
            file_path = self._normalize_path(str(file_info.path))
            current_hashes[file_path] = file_info.content_hash

            previous_hash = self._cached_hashes.get(file_path)
            if previous_hash is None:
                new_paths.append(file_path)
                changed_files.append(file_info)
            elif previous_hash != file_info.content_hash:
                changed_files.append(file_info)
            else:
                unchanged_files.append(file_info)

        deleted_paths = sorted(set(self._cached_hashes.keys()) - set(current_hashes.keys()))

        return IncrementalDiff(
            changed_files=changed_files,
            unchanged_files=unchanged_files,
            deleted_paths=deleted_paths,
            new_paths=sorted(new_paths),
        )

    def save(self, files: list[FileInfo]) -> None:
        """Persist cache from current scanned files."""
        current_hashes = {
            self._normalize_path(str(file_info.path)): file_info.content_hash
            for file_info in files
        }
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(current_hashes, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self._cached_hashes = current_hashes

    def _load_cache(self) -> dict[str, str]:
        if not self.cache_path.exists():
            return {}

        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            normalized: dict[str, str] = {}
            for path, content_hash in data.items():
                if isinstance(path, str) and isinstance(content_hash, str):
                    normalized[self._normalize_path(path)] = content_hash
            return normalized
        except Exception as exc:
            logger.warning("Failed to load incremental cache %s: %s", self.cache_path, exc)
            return {}

    def _normalize_path(self, file_path: str) -> str:
        return file_path.replace("\\", "/").lstrip("./")

