"""Agentic orchestration primitives for HOM-LLM."""

from homllm.agent.contracts import (
    AgenticMode,
    TaskClass,
    ToolResult,
    VerificationGateResult,
)
from homllm.agent.manifests import SubagentManifest, SubagentStatus
from homllm.agent.orchestrator import (
    AgenticIterationSnapshot,
    ReadOnlyPlannerDecision,
    agentic_pass_signature,
    apply_read_only_iteration_retrieval_config,
    build_read_only_planner_prompt,
    default_followup_overrides,
    invoke_read_only_planner,
    normalize_planner_action,
    sanitize_planner_overrides,
)
from homllm.agent.permissions import PermissionDecision, PermissionMode, ToolPermissionSpec
from homllm.agent.router import (
    RouteDecision,
    intent_to_task_class,
    resolve_agentic_mode,
    route_agentic_mode,
)
from homllm.agent.state import (
    EvidenceAttempt,
    EvidenceState,
    ExecutionState,
    PlanState,
    PlanStep,
    PlanStepStatus,
    TaskState,
    VerificationState,
)
from homllm.agent.stopping import LoopBudget, RepetitionGuard, StopReason

__all__ = [
    "AgenticMode",
    "TaskClass",
    "ToolResult",
    "VerificationGateResult",
    "SubagentManifest",
    "SubagentStatus",
    "AgenticIterationSnapshot",
    "ReadOnlyPlannerDecision",
    "agentic_pass_signature",
    "apply_read_only_iteration_retrieval_config",
    "build_read_only_planner_prompt",
    "default_followup_overrides",
    "invoke_read_only_planner",
    "normalize_planner_action",
    "sanitize_planner_overrides",
    "PermissionDecision",
    "PermissionMode",
    "ToolPermissionSpec",
    "RouteDecision",
    "intent_to_task_class",
    "resolve_agentic_mode",
    "route_agentic_mode",
    "EvidenceAttempt",
    "EvidenceState",
    "ExecutionState",
    "PlanState",
    "PlanStep",
    "PlanStepStatus",
    "TaskState",
    "VerificationState",
    "LoopBudget",
    "RepetitionGuard",
    "StopReason",
]
