from dataclasses import replace
from pathlib import Path
from typing import Any
import yaml

from homllm.common.config import Config
from homllm.indexer.pipeline import IndexerPipeline
from homllm_v4.contracts.index import (
    IndexFreshness,
    IndexRequest,
    IndexValidation,
    RepoIndexManifest,
)


class V3IndexAdapter:
    def validate(self, request: IndexRequest) -> IndexValidation:
        artifact_paths = {name: str(Path(path)) for name, path in request.artifact_paths.items()}
        artifact_mtimes = [
            Path(path).stat().st_mtime
            for path in artifact_paths.values()
            if Path(path).exists()
        ]
        latest_artifact_mtime = max(artifact_mtimes, default=0.0)
        indexed_at = str(latest_artifact_mtime)
        workspace_root = Path(request.workspace_root)
        stale_file_count = self._count_files_newer_than(workspace_root, latest_artifact_mtime)
        freshness = IndexFreshness(
            status="possibly_stale" if stale_file_count else "fresh",
            reason="workspace files are newer than index artifacts" if stale_file_count else None,
            indexed_at=indexed_at,
            workspace_changed_since_index=bool(stale_file_count),
            stale_file_count=stale_file_count,
            untracked_file_count=0,
        )
        manifest = RepoIndexManifest(
            index_id="v3-adapter-index",
            workspace_root=request.workspace_root,
            schema_version="unknown",
            created_at=indexed_at,
            last_indexed_at=indexed_at,
            source_file_count=0,
            chunk_count=0,
            symbol_count=0,
            relation_count=0,
            embedding_model="unknown",
            embedding_dimension=0,
            artifact_paths=artifact_paths,
            ignored_paths_summary={},
            warnings=(),
        )
        return IndexValidation(manifest=manifest, freshness=freshness)

    @staticmethod
    def _count_files_newer_than(workspace_root: Path, mtime: float) -> int:
        if not workspace_root.exists():
            return 0
        count = 0
        for path in workspace_root.rglob("*"):
            if ".git" in path.parts or ".homllm" in path.parts:
                continue
            if path.is_file() and path.stat().st_mtime > mtime:
                count += 1
        return count


def build_v3_agent_task_index(
    *,
    config_path: Path,
    workspace_root: Path,
    artifact_paths: dict[str, str],
    incremental: bool = False,
    skip_vectors: bool = False,
) -> dict[str, object]:
    config = Config.from_file(Path(config_path))
    indexer_config = config.get_indexer_config()
    if skip_vectors:
        indexer_config = replace(indexer_config, vector_indexing_enabled=False)
    IndexerPipeline(indexer_config).index(Path(workspace_root), incremental=incremental)
    return _index_metrics(Path(artifact_paths["artifacts"]))


def _index_metrics(artifact_root: Path) -> dict[str, object]:
    metrics: dict[str, object] = {}
    symbols_path = artifact_root / "symbols.json"
    files_path = artifact_root / "files.json"
    if symbols_path.exists():
        data = yaml.safe_load(symbols_path.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            metrics["symbol_count"] = len(data.get("symbols", []))
    if files_path.exists():
        data = yaml.safe_load(files_path.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            files = data.get("files", data)
            metrics["source_file_count"] = len(files) if hasattr(files, "__len__") else 0
    return metrics

