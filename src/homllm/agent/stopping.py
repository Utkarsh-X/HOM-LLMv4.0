"""Stopping logic helpers for bounded orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StopReason(str, Enum):
    """Canonical stop reasons for orchestration loops."""

    COMPLETED = "completed"
    MAX_ITERATIONS = "max_iterations"
    REPEATED_NO_PROGRESS = "repeated_no_progress"
    VERIFICATION_BLOCK = "verification_block"
    COMMAND_FAILURE_BUDGET = "command_failure_budget"
    MANUAL_INTERRUPT = "manual_interrupt"


@dataclass(frozen=True)
class LoopBudget:
    """Hard caps for orchestration."""

    max_iterations: int = 4
    max_repeated_signature: int = 2
    max_command_failures: int = 2

    def __post_init__(self):
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        if self.max_repeated_signature < 1:
            raise ValueError("max_repeated_signature must be >= 1")
        if self.max_command_failures < 0:
            raise ValueError("max_command_failures must be >= 0")


@dataclass
class RepetitionGuard:
    """Track repeated signatures to prevent low-value loops."""

    max_repeated_signature: int = 2
    _seen: dict[str, int] = field(default_factory=dict)

    def register(self, signature: str) -> int:
        """Record signature and return the updated count."""
        next_count = self._seen.get(signature, 0) + 1
        self._seen[signature] = next_count
        return next_count

    def should_stop(self, signature: str) -> bool:
        """Return True when repeated count exceeds allowed budget."""
        return self._seen.get(signature, 0) > self.max_repeated_signature

