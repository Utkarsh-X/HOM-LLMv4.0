"""State types for bounded agentic orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from homllm.agent.contracts import AgenticMode, TaskClass, VerificationGateResult


class PlanStepStatus(str, Enum):
    """Execution status for a plan step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class PlanStep:
    """Single step in a bounded plan."""

    step_id: str
    description: str
    status: PlanStepStatus = PlanStepStatus.PENDING
    notes: str = ""


@dataclass(frozen=True)
class PlanState:
    """Plan state tracked by the orchestrator."""

    steps: tuple[PlanStep, ...] = ()
    active_step_id: Optional[str] = None

    @property
    def has_blocked_steps(self) -> bool:
        return any(step.status == PlanStepStatus.BLOCKED for step in self.steps)


@dataclass(frozen=True)
class EvidenceAttempt:
    """Telemetry for one evidence acquisition attempt."""

    query: str
    retrieved_count: int
    ranked_count: int
    context_tokens: int
    insufficiency_detected: bool = False


@dataclass(frozen=True)
class EvidenceState:
    """Aggregated evidence state across attempts."""

    attempts: tuple[EvidenceAttempt, ...] = ()
    selected_doc_ids: tuple[str, ...] = ()
    context_artifact_id: Optional[str] = None


@dataclass(frozen=True)
class VerificationState:
    """Verification results accumulated during orchestration."""

    required_gates: tuple[str, ...] = ()
    gate_results: tuple[VerificationGateResult, ...] = ()

    @property
    def has_blocking_failures(self) -> bool:
        return any((not result.passed) and result.blocking for result in self.gate_results)


@dataclass(frozen=True)
class ExecutionState:
    """Execution traces for runtime checks."""

    commands_run: tuple[str, ...] = ()
    successful_commands: int = 0
    failed_commands: int = 0


@dataclass(frozen=True)
class TaskState:
    """Top-level task state for one agentic run."""

    task_id: str
    query: str
    mode: AgenticMode = AgenticMode.SINGLE_PASS
    task_class: TaskClass = TaskClass.UNKNOWN
    iteration: int = 0
    max_iterations: int = 1
    llm_call_count: int = 0
    tool_call_count: int = 0
    stop_reason: Optional[str] = None
    plan: PlanState = field(default_factory=PlanState)
    evidence: EvidenceState = field(default_factory=EvidenceState)
    verification: VerificationState = field(default_factory=VerificationState)
    execution: ExecutionState = field(default_factory=ExecutionState)
