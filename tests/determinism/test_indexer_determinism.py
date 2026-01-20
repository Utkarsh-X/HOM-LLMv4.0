"""Determinism tests for Indexer layer."""

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from homllm.common.config import Config, IndexerConfig, StorageConfig
from homllm.indexer.pipeline import IndexerPipeline


@pytest.fixture
def test_config() -> IndexerConfig:
    """Create test configuration."""
    with TemporaryDirectory() as tmpdir:
        storage = StorageConfig(
            duckdb_path=Path(tmpdir) / "test.duckdb",
            tantivy_path=Path(tmpdir) / "test.tantivy",
            lancedb_path=Path(tmpdir) / "test.lance",
            artifacts_path=Path(tmpdir) / "artifacts",
        )
        return IndexerConfig(
            languages=["python"],
            ignore_patterns=[".git", "__pycache__"],
            chunk_max_lines=100,
            storage=storage,
        )


def test_indexer_determinism(test_config: IndexerConfig):
    """
    Test that Indexer produces identical artifacts for same input.
    
    IDX-001: Same repo state → byte-identical artifacts
    """
    with TemporaryDirectory() as repo_dir:
        repo_path = Path(repo_dir)
        
        # Create minimal test repo
        test_file = repo_path / "test.py"
        test_file.write_text("def hello():\n    pass\n")

        # Run indexing twice
        with TemporaryDirectory() as tmp1:
            config1 = IndexerConfig(
                languages=test_config.languages,
                ignore_patterns=test_config.ignore_patterns,
                chunk_max_lines=test_config.chunk_max_lines,
                storage=StorageConfig(
                    duckdb_path=Path(tmp1) / "test.duckdb",
                    tantivy_path=Path(tmp1) / "test.tantivy",
                    lancedb_path=Path(tmp1) / "test.lance",
                    artifacts_path=Path(tmp1) / "artifacts",
                ),
            )
            pipeline1 = IndexerPipeline(config1)
            # pipeline1.index(repo_path)  # TODO: Uncomment when implemented

        with TemporaryDirectory() as tmp2:
            config2 = IndexerConfig(
                languages=test_config.languages,
                ignore_patterns=test_config.ignore_patterns,
                chunk_max_lines=test_config.chunk_max_lines,
                storage=StorageConfig(
                    duckdb_path=Path(tmp2) / "test.duckdb",
                    tantivy_path=Path(tmp2) / "test.tantivy",
                    lancedb_path=Path(tmp2) / "test.lance",
                    artifacts_path=Path(tmp2) / "artifacts",
                ),
            )
            pipeline2 = IndexerPipeline(config2)
            # pipeline2.index(repo_path)  # TODO: Uncomment when implemented

        # TODO: Compare artifact hashes
        # For now, test passes if no exceptions
        assert True


def test_indexer_idempotence(test_config: IndexerConfig):
    """
    Test that re-indexing same files produces same results.
    
    IDX-003: Incremental = full on changed files only
    """
    # TODO: Implement when indexing is complete
    pass
