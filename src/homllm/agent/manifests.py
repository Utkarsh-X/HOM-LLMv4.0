"""Manifest types for subagent lifecycle tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class SubagentStatus(str, Enum):
    """Subagent execution status."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class SubagentManifest:
    """Structured manifest for one subagent task."""

    subagent_id: str
    role: str
    status: SubagentStatus
    task_summary: str
    created_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize manifest to a JSON-friendly dictionary."""
        return {
            "subagent_id": self.subagent_id,
            "role": self.role,
            "status": self.status.value,
            "task_summary": self.task_summary,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "result_payload": self.result_payload,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SubagentManifest":
        """Deserialize manifest from a dictionary."""
        return cls(
            subagent_id=str(payload.get("subagent_id", "")),
            role=str(payload.get("role", "")),
            status=SubagentStatus(str(payload.get("status", "running"))),
            task_summary=str(payload.get("task_summary", "")),
            created_at=str(payload.get("created_at", "")),
            completed_at=payload.get("completed_at"),
            error=payload.get("error"),
            result_payload=dict(payload.get("result_payload") or {}),
        )

