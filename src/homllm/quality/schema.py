"""
Data schema for context quality metrics.

Immutable, serializable record of a single query's quality evaluation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class MetricRecord:
    """Single query's context quality metrics. Immutable, serializable."""

    # Identity
    query_id: str
    run_id: str
    timestamp_utc: str

    # Stage: Ranking (computed post-ranking)
    score_separation: float       # M5: CV of final scores
    reranker_influence: float     # M6: reranker variance share

    # Stage: Context (computed post-context-assembly)
    semantic_strength: float      # M1: mean CE score of context blocks
    query_term_recall: float      # M2: fraction of query terms in context
    file_entropy: float           # M3: normalized file entropy
    content_overlap: float        # M4: mean pairwise Jaccard
    budget_utilization: float     # M7: used_tokens / token_budget

    # Context metadata (for normalization window)
    block_count: int
    unique_file_count: int
    candidate_count: int
    reranker_available: bool

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @staticmethod
    def utc_now() -> str:
        """Current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class MetricStorage:
    """Append-only JSONL storage for metric records."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: MetricRecord) -> None:
        """Append a single record to the JSONL file."""
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(record.to_json() + "\n")

    def read_all(self) -> list[MetricRecord]:
        """Read all records from the JSONL file."""
        if not self.path.exists():
            return []
        records = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                records.append(MetricRecord(**data))
        return records
