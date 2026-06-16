from pathlib import Path

from homllm_v4.contracts.index import IndexRequest
from homllm_v4.services.index_service import IndexService


def test_missing_index_artifacts_return_index_missing(tmp_path: Path) -> None:
    service = IndexService()

    result = service.validate(
        IndexRequest(
            workspace_root=str(tmp_path),
            include_patterns=("**/*.py",),
            exclude_patterns=(".git/**",),
            language_profile="python",
            mode="validate",
            artifact_paths={"duckdb": str(tmp_path / "missing.duckdb")},
        )
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "index_missing"


def test_present_artifact_paths_produce_manifest(tmp_path: Path) -> None:
    duckdb = tmp_path / "index.duckdb"
    bm25 = tmp_path / "bm25"
    vector = tmp_path / "vectors"
    duckdb.write_text("fake", encoding="utf-8")
    bm25.mkdir()
    vector.mkdir()
    service = IndexService()

    result = service.validate(
        IndexRequest(
            workspace_root=str(tmp_path),
            include_patterns=("**/*.py",),
            exclude_patterns=(".git/**",),
            language_profile="python",
            mode="validate",
            artifact_paths={
                "duckdb": str(duckdb),
                "bm25": str(bm25),
                "vector": str(vector),
            },
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.manifest.workspace_root == str(tmp_path)
    assert result.output.manifest.artifact_paths["duckdb"] == str(duckdb)
    assert result.output.freshness.status in {"fresh", "possibly_stale"}


def test_validate_mode_does_not_rebuild_index(tmp_path: Path) -> None:
    service = IndexService()

    result = service.validate(
        IndexRequest(
            workspace_root=str(tmp_path),
            include_patterns=("**/*.py",),
            exclude_patterns=(),
            language_profile="python",
            mode="validate",
            artifact_paths={},
        )
    )

    assert result.ok is False
    assert not any(tmp_path.glob("*.duckdb"))
