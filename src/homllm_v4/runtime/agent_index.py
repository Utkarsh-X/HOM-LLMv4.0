from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from homllm_v4.adapters.v3_index_adapter import build_v3_agent_task_index


@dataclass(frozen=True)
class AgentIndexPrepRequest:
    template_config_path: Path
    workspace_root: Path
    artifact_root: Path
    run_id: str
    index_artifact_dir: Path | None = None
    incremental: bool = False
    skip_vectors: bool = False
    index_builder: Any = None


@dataclass(frozen=True)
class AgentIndexPrepResult:
    config_path: Path
    artifact_paths: dict[str, str]
    built: bool
    metrics: dict[str, object]


def prepare_agent_task_index(request: AgentIndexPrepRequest) -> AgentIndexPrepResult:
    template_config_path = Path(request.template_config_path).resolve()
    workspace_root = Path(request.workspace_root).resolve()
    artifact_root = Path(request.artifact_root).resolve()
    index_root = (
        Path(request.index_artifact_dir).resolve()
        if request.index_artifact_dir is not None
        else artifact_root / request.run_id / "index"
    )
    index_root.mkdir(parents=True, exist_ok=True)

    config_data = _load_config_data(template_config_path)
    artifact_paths = {
        "artifacts": _path_string(index_root),
        "duckdb": _path_string(index_root / "metadata.duckdb"),
        "tantivy": _path_string(index_root / "bm25.index"),
        "lancedb": _path_string(index_root / "vectors.lance"),
    }
    indexer = config_data.setdefault("indexer", {})
    storage = indexer.setdefault("storage", {})
    storage["artifacts_path"] = artifact_paths["artifacts"]
    storage["duckdb_path"] = artifact_paths["duckdb"]
    storage["tantivy_path"] = artifact_paths["tantivy"]
    storage["lancedb_path"] = artifact_paths["lancedb"]
    if request.skip_vectors:
        indexer["vector_indexing_enabled"] = False

    generated_config_path = index_root / "generated_config.yaml"
    generated_config_path.write_text(
        yaml.safe_dump(config_data, sort_keys=False),
        encoding="utf-8",
    )

    builder = request.index_builder or build_v3_agent_task_index
    metrics = builder(
        config_path=generated_config_path,
        workspace_root=workspace_root,
        artifact_paths=artifact_paths,
        incremental=request.incremental,
        skip_vectors=request.skip_vectors,
    )
    return AgentIndexPrepResult(
        config_path=generated_config_path.resolve(),
        artifact_paths=artifact_paths,
        built=True,
        metrics=dict(metrics or {}),
    )


def _load_config_data(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid_index_template_config:{path}")
    return data


def _path_string(path: Path) -> str:
    return path.resolve().as_posix()

