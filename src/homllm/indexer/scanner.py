"""File scanner implementation."""

import hashlib
import fnmatch
from pathlib import Path
from typing import Iterator

from homllm.common.types import FileInfo
from homllm.indexer.interfaces import FileScanner, ScanConfig


# Language to extension mapping
LANGUAGE_EXTENSIONS = {
    "python": {".py", ".pyi"},
    "javascript": {".js", ".mjs", ".cjs"},
    "typescript": {".ts", ".tsx"},
    "java": {".java"},
    "go": {".go"},
    "rust": {".rs"},
    "cpp": {".cpp", ".cc", ".cxx", ".hpp", ".h"},
    "c": {".c", ".h"},
}


class RipgrepScanner(FileScanner):
    """File scanner for code discovery."""

    def __init__(self):
        """Initialize scanner."""
        self._gitignore_patterns: list[str] = []

    def _load_gitignore(self, repo_path: Path) -> None:
        """Load .gitignore patterns."""
        gitignore_path = repo_path / ".gitignore"
        if gitignore_path.exists():
            with open(gitignore_path, "r", encoding="utf-8") as f:
                self._gitignore_patterns = [
                    line.strip() for line in f if line.strip() and not line.startswith("#")
                ]

    def _should_ignore(self, file_path: Path, repo_path: Path) -> bool:
        """Check if file should be ignored based on .gitignore and config patterns."""
        rel_path = file_path.relative_to(repo_path)
        rel_str = str(rel_path).replace("\\", "/")

        # Check config ignore patterns
        for pattern in self._config.ignore_patterns:
            if fnmatch.fnmatch(rel_str, pattern) or fnmatch.fnmatch(
                rel_str, f"**/{pattern}"
            ):
                return True

        # Check .gitignore patterns
        for pattern in self._gitignore_patterns:
            if fnmatch.fnmatch(rel_str, pattern) or fnmatch.fnmatch(
                rel_str, f"**/{pattern}"
            ):
                return True

        return False

    def _get_language(self, file_path: Path) -> str | None:
        """Detect language from file extension."""
        ext = file_path.suffix.lower()
        for lang, exts in LANGUAGE_EXTENSIONS.items():
            if ext in exts:
                return lang
        return None

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute deterministic content hash."""
        # Use SHA256 for deterministic hashing
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _count_lines(self, file_path: Path) -> int:
        """Count lines in file efficiently."""
        try:
            with open(file_path, "rb") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

    def scan(self, repo_path: Path, config: ScanConfig) -> Iterator[FileInfo]:
        """
        Yields file metadata without loading content.
        
        Properties:
        - Respects .gitignore by default
        - Language filters are config-driven
        - Returns deterministic ordering (sorted by path)
        """
        self._config = config
        self._load_gitignore(repo_path)

        # Collect all matching files first for deterministic ordering
        files: list[Path] = []
        repo_path = repo_path.resolve()

        # Get allowed extensions from config languages
        allowed_extensions: set[str] = set()
        for lang in config.languages:
            if lang in LANGUAGE_EXTENSIONS:
                allowed_extensions.update(LANGUAGE_EXTENSIONS[lang])

        # Walk directory tree
        for file_path in repo_path.rglob("*"):
            if not file_path.is_file():
                continue

            # Check language filter
            if allowed_extensions and file_path.suffix.lower() not in allowed_extensions:
                continue

            # Check ignore patterns
            if self._should_ignore(file_path, repo_path):
                continue

            files.append(file_path)

        # Sort for deterministic ordering
        files.sort(key=lambda p: str(p))

        # Generate FileInfo for each file
        for file_path in files:
            try:
                language = self._get_language(file_path)
                content_hash = self._compute_file_hash(file_path)
                line_count = self._count_lines(file_path)
                rel_path = file_path.relative_to(repo_path)
                rel_posix = rel_path.as_posix()

                # Generate deterministic file_id from path and hash
                file_id = hashlib.sha256(
                    f"{rel_posix}:{content_hash}".encode()
                ).hexdigest()[:16]

                yield FileInfo(
                    file_id=file_id,
                    path=Path(rel_posix),
                    language=language,
                    content_hash=content_hash,
                    line_count=line_count,
                    parse_error=False,
                )
            except Exception:
                # Skip files that can't be read
                continue
