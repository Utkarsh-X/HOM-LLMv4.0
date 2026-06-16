from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class IndexRequest:
    workspace_root: str
    include_patterns: tuple[str, ...]
    exclude_patterns: tuple[str, ...]
    language_profile: str
    mode: Literal["load", "validate", "rebuild", "incremental"]
    artifact_paths: dict[str, str] = field(default_factory=dict)
    max_index_age_seconds: int | None = None
    force: bool = False


@dataclass(frozen=True)
class RepoIndexManifest:
    index_id: str
    workspace_root: str
    schema_version: str
    created_at: str
    last_indexed_at: str
    source_file_count: int
    chunk_count: int
    symbol_count: int
    relation_count: int
    embedding_model: str
    embedding_dimension: int
    artifact_paths: dict[str, str]
    ignored_paths_summary: dict[str, int]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class IndexFreshness:
    status: Literal["fresh", "possibly_stale", "stale"]
    reason: str | None
    indexed_at: str
    workspace_changed_since_index: bool
    stale_file_count: int
    untracked_file_count: int


@dataclass(frozen=True)
class IndexValidation:
    manifest: RepoIndexManifest
    freshness: IndexFreshness
