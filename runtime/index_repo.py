#!/usr/bin/env python3
"""
Canonical entrypoint for indexing a repository.

Usage:
    python runtime/index_repo.py --repo <path> [--config <path>] [--incremental] [--json]
"""
import argparse
import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
import logging

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import bootstrap

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from homllm.common.config import Config
from homllm.indexer.pipeline import IndexerPipeline
from runtime.logger import configure_logging


def format_duration_ms(start: float, end: float) -> float:
    """Convert duration to milliseconds."""
    return (end - start) * 1000


logger = configure_logging(logger_name=__name__)


def print_telemetry(phase: str, **kwargs):
    """Print telemetry line in consistent format."""
    parts = [f"[{phase}]"]
    for key, value in kwargs.items():
        if isinstance(value, float):
            parts.append(f"{key}={value:.2f}")
        else:
            parts.append(f"{key}={value}")
    logger.info(" ".join(parts))


class IndexingTelemetry:
    """Telemetry collector for indexing."""

    def __init__(self, repo_path: Path, export_json: bool = False, progress_interval_sec: int = 5):
        self.repo_path = repo_path
        self.export_json = export_json
        self.progress_interval_sec = progress_interval_sec
        self.start_time = None
        self.end_time = None
        self.files_scanned = 0
        self.symbols_extracted = 0
        self.artifacts_written = []
        self.progress_updates = []
        self._stop_progress = False
        self._progress_thread = None

    def start(self):
        """Mark start of indexing."""
        self.start_time = time.perf_counter()
        print_telemetry("INDEX", status="start", repo=str(self.repo_path))
        
        # Start progress thread
        self._stop_progress = False
        self._progress_thread = threading.Thread(target=self._progress_loop, daemon=True)
        self._progress_thread.start()

    def _progress_loop(self):
        """Periodically print progress updates."""
        while not self._stop_progress:
            time.sleep(self.progress_interval_sec)
            if not self._stop_progress and self.start_time:
                elapsed_ms = format_duration_ms(self.start_time, time.perf_counter())
                print_telemetry("INDEX", status="processing", elapsed_ms=f"{elapsed_ms:.0f}")

    def stop_progress(self):
        """Stop progress updates."""
        self._stop_progress = True
        if self._progress_thread:
            self._progress_thread.join(timeout=1.0)

    def record_scan(self, files_count: int):
        """Record file scan results."""
        self.files_scanned = files_count

    def record_symbols(self, symbols_count: int):
        """Record symbols extracted."""
        self.symbols_extracted = symbols_count

    def record_artifact(self, artifact_path: str):
        """Record artifact written."""
        self.artifacts_written.append(artifact_path)

    def finish(self):
        """Mark end of indexing and print summary."""
        self.end_time = time.perf_counter()
        duration_ms = format_duration_ms(self.start_time, self.end_time)

        print_telemetry(
            "INDEX",
            files=self.files_scanned,
            symbols=self.symbols_extracted,
            duration_ms=f"{duration_ms:.0f}",
        )

        # Print artifact paths
        for artifact in self.artifacts_written:
            print_telemetry("INDEX", artifact=artifact)

        # Export JSON if requested
        if self.export_json:
            self._export_json()

    def _export_json(self):
        """Export telemetry as JSON."""
        telemetry_data = {
            "phase": "indexing",
            "repo_path": str(self.repo_path),
            "start_time": datetime.utcnow().isoformat() if self.start_time else None,
            "end_time": datetime.utcnow().isoformat() if self.end_time else None,
            "duration_ms": format_duration_ms(self.start_time, self.end_time) if self.end_time else None,
            "files_scanned": self.files_scanned,
            "symbols_extracted": self.symbols_extracted,
            "artifacts_written": self.artifacts_written,
            "progress_updates": self.progress_updates,
        }

        # Write to indexes/index_telemetry.json
        output_path = Path("indexes") / "index_telemetry.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(telemetry_data, f, indent=2)

        print_telemetry("INDEX", json_export=str(output_path))


# Note: Progress tracking is done by monitoring the indexing process
# We'll track progress by checking file counts during indexing


def main():
    """Main entrypoint."""
    parser = argparse.ArgumentParser(description="Index a repository")
    parser.add_argument("--repo", type=Path, required=True, help="Repository path to index")
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"), help="Config file path")
    parser.add_argument("--incremental", action="store_true", help="Incremental indexing")
    parser.add_argument("--json", action="store_true", help="Export JSON telemetry")
    parser.add_argument("--progress-interval", type=int, default=10, help="Progress update interval (files)")

    args = parser.parse_args()

    # Validate repo path
    if not args.repo.exists():
        logger.error(f"Error: Repository path does not exist: {args.repo}")
        sys.exit(1)

    # Load config
    if not args.config.exists():
        logger.error(f"Error: Config file does not exist: {args.config}")
        sys.exit(1)

    try:
        config = Config.from_file(args.config)
        indexer_config = config.get_indexer_config()
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        sys.exit(1)

    # Initialize telemetry
    telemetry = IndexingTelemetry(args.repo, export_json=args.json, progress_interval_sec=args.progress_interval)
    telemetry.start()

    # Create pipeline
    pipeline = IndexerPipeline(indexer_config)

    try:
        # Run indexing (progress will be tracked via periodic updates)
        pipeline.index(args.repo, incremental=args.incremental)
        
        # Stop progress updates
        telemetry.stop_progress()

        # Read symbol count from artifacts
        artifacts_path = indexer_config.storage.artifacts_path
        symbols_file = Path(artifacts_path) / "symbols.json"
        if symbols_file.exists():
            with open(symbols_file) as f:
                symbols_data = json.load(f)
                telemetry.record_symbols(len(symbols_data.get("symbols", [])))

        # Record artifacts
        artifacts_path_obj = Path(artifacts_path)
        for artifact_name in ["symbols.json", "files.json", "callgraph.json", "dependencies.json"]:
            artifact_path = artifacts_path_obj / artifact_name
            if artifact_path.exists():
                telemetry.record_artifact(str(artifact_path))

        # Record index directories
        for index_name in ["bm25.index", "vectors.lance", "metadata.duckdb"]:
            index_path = artifacts_path_obj / index_name
            if index_path.exists():
                telemetry.record_artifact(str(index_path))

        telemetry.finish()

    except Exception as e:
        logger.error(f"Error during indexing: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
