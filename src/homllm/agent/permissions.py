"""Permission model for agentic tool execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PermissionMode(str, Enum):
    """Permission levels for agentic tools."""

    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    DANGER_FULL_ACCESS = "danger_full_access"


@dataclass(frozen=True)
class ToolPermissionSpec:
    """Required permission for a tool."""

    tool_name: str
    required_mode: PermissionMode


@dataclass(frozen=True)
class PermissionDecision:
    """Permission decision emitted by policy."""

    allowed: bool
    required_mode: PermissionMode
    current_mode: PermissionMode
    reason: Optional[str] = None
    requires_user_approval: bool = False


def permission_satisfies(current: PermissionMode, required: PermissionMode) -> bool:
    """Return True if current mode is sufficient for required mode."""
    order = {
        PermissionMode.READ_ONLY: 1,
        PermissionMode.WORKSPACE_WRITE: 2,
        PermissionMode.DANGER_FULL_ACCESS: 3,
    }
    return order[current] >= order[required]

