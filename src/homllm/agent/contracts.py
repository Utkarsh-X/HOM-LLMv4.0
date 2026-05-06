"""Typed contracts for agentic orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AgenticMode(str, Enum):
    """Execution mode for a task."""

    SINGLE_PASS = "single_pass"
    READ_ONLY_AGENTIC = "read_only_agentic"
    VERIFICATION = "verification"
    EXECUTION = "execution"
    PATCH = "patch"


class TaskClass(str, Enum):
    """High-level task class used by the router."""

    EXPLAIN = "explain"
    IMPLEMENT = "implement"
    REFACTOR = "refactor"
    DEBUG = "debug"
    SEARCH = "search"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ToolResult:
    """Normalized tool result contract."""

    tool_name: str
    ok: bool
    payload: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: int = 0
    attempt_index: int = 1


@dataclass(frozen=True)
class VerificationGateResult:
    """Result for a single verification gate."""

    gate_name: str
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)
    blocking: bool = True

