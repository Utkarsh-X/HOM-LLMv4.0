"""
Data loaders for diagnostic framework.

All loaders are READ-ONLY and never modify source data.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class TelemetryData:
    """Immutable telemetry data from a run."""
    
    run_id: str
    query: str
    phases: dict[str, dict[str, Any]]
    raw_data: dict[str, Any]


@dataclass(frozen=True)
class IndexMetadata:
    """Immutable index metadata."""
    
    files: tuple[dict[str, Any], ...]
    symbols: tuple[dict[str, Any], ...]
    callgraph: dict[str, Any]


@dataclass(frozen=True)
class QueryData:
    """Immutable query data."""
    
    query_id: int
    query_text: str


@dataclass(frozen=True)
class ResponseData:
    """Immutable response data from eval run."""
    
    query_id: int
    query_text: str
    run_id: str
    telemetry_path: str
    tokens_in: int
    tokens_out: int
    latency_ms: float
    status: str


class TelemetryLoader:
    """
    Loads telemetry data from artifacts/runs/<run_id>/telemetry.json.
    
    Read-only: Never modifies source artifacts.
    """
    
    def __init__(self, artifacts_path: Path):
        self.artifacts_path = Path(artifacts_path)
        self.runs_path = self.artifacts_path / "runs"
    
    def list_runs(self) -> list[str]:
        """List all available run IDs."""
        if not self.runs_path.exists():
            return []
        return [d.name for d in self.runs_path.iterdir() if d.is_dir()]
    
    def load(self, run_id: str) -> Optional[TelemetryData]:
        """Load telemetry for a specific run."""
        telemetry_file = self.runs_path / run_id / "telemetry.json"
        if not telemetry_file.exists():
            return None
        
        try:
            with open(telemetry_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            return TelemetryData(
                run_id=data.get("run_id", run_id),
                query=data.get("query", ""),
                phases=data.get("phases", {}),
                raw_data=data,
            )
        except (json.JSONDecodeError, IOError):
            return None


class IndexLoader:
    """
    Loads index metadata from indexes/ directory.
    
    Read-only: Never modifies index artifacts.
    """
    
    def __init__(self, indexes_path: Path):
        self.indexes_path = Path(indexes_path)
    
    def load(self) -> Optional[IndexMetadata]:
        """Load all index metadata."""
        try:
            files = self._load_json("files.json").get("files", [])
            symbols = self._load_json("symbols.json").get("symbols", [])
            callgraph = self._load_json("callgraph.json")
            
            return IndexMetadata(
                files=tuple(files),
                symbols=tuple(symbols),
                callgraph=callgraph,
            )
        except Exception:
            return None
    
    def _load_json(self, filename: str) -> dict:
        """Load a JSON file from indexes directory."""
        filepath = self.indexes_path / filename
        if not filepath.exists():
            return {}
        
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)


class QueryLoader:
    """
    Loads query definitions from eval/queries.json.
    
    Read-only: Never modifies query files.
    """
    
    def __init__(self, eval_path: Path):
        self.eval_path = Path(eval_path)
    
    def load(self) -> list[QueryData]:
        """Load all queries."""
        queries_file = self.eval_path / "queries.json"
        if not queries_file.exists():
            return []
        
        try:
            with open(queries_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            return [
                QueryData(
                    query_id=q.get("query_id", 0),
                    query_text=q.get("query_text", ""),
                )
                for q in data.get("queries", [])
            ]
        except (json.JSONDecodeError, IOError):
            return []
    
    def get_by_id(self, query_id: int) -> Optional[QueryData]:
        """Get a specific query by ID."""
        queries = self.load()
        for q in queries:
            if q.query_id == query_id:
                return q
        return None


class ResponseLoader:
    """
    Loads response data from eval/runs/<run_dir>/responses.jsonl.
    
    Read-only: Never modifies response files.
    """
    
    def __init__(self, eval_path: Path):
        self.eval_path = Path(eval_path)
        self.runs_path = self.eval_path / "runs"
    
    def list_runs(self) -> list[str]:
        """List all available eval run directories."""
        if not self.runs_path.exists():
            return []
        return [d.name for d in self.runs_path.iterdir() if d.is_dir()]
    
    def load(self, run_dir: str) -> list[ResponseData]:
        """Load all responses from an eval run."""
        responses_file = self.runs_path / run_dir / "responses.jsonl"
        if not responses_file.exists():
            return []
        
        responses = []
        try:
            with open(responses_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    data = json.loads(line)
                    responses.append(ResponseData(
                        query_id=data.get("query_id", 0),
                        query_text=data.get("query_text", ""),
                        run_id=data.get("run_id", ""),
                        telemetry_path=data.get("telemetry_path", ""),
                        tokens_in=data.get("tokens_in", 0),
                        tokens_out=data.get("tokens_out", 0),
                        latency_ms=data.get("latency_ms", 0.0),
                        status=data.get("status", ""),
                    ))
        except (json.JSONDecodeError, IOError):
            pass
        
        return responses
    
    def get_latest_run(self) -> Optional[str]:
        """Get the most recent eval run directory."""
        runs = self.list_runs()
        if not runs:
            return None
        # Sort by name (assumes run_YYYYMMDD_HHMMSS format)
        return sorted(runs, reverse=True)[0]
