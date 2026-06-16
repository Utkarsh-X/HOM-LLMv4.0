from dataclasses import dataclass


@dataclass(frozen=True)
class FilePatch:
    file_path: str
    expected_content_hash: str | None
    new_content: str


@dataclass(frozen=True)
class PatchApplyRequest:
    task_id: str
    workspace_root: str
    patches: tuple[FilePatch, ...]
    dry_run: bool = False
    allowed_file_paths: tuple[str, ...] = ()
    max_file_changes: int | None = None


@dataclass(frozen=True)
class FilePatchResult:
    file_path: str
    old_content_hash: str | None
    new_content_hash: str
    diff: str
    old_content: str | None = None
    old_file_existed: bool = True


@dataclass(frozen=True)
class PatchApplyResult:
    applied: bool
    file_results: tuple[FilePatchResult, ...]


@dataclass(frozen=True)
class PatchRollbackRequest:
    task_id: str
    workspace_root: str
    file_results: tuple[FilePatchResult, ...]


@dataclass(frozen=True)
class PatchRollbackResult:
    rolled_back: bool
    restored_files: tuple[str, ...]
    deleted_files: tuple[str, ...]
