from dataclasses import dataclass, field
from typing import Literal

from homllm_v4.contracts.edit_proposal import EditProposalEvidenceContext


AGENT_ACTION_READ_FILE = "read_file"
AGENT_ACTION_SEARCH_REPO = "search_repo"
AGENT_ACTION_PROPOSE_PATCH = "propose_patch"
AGENT_ACTION_FINISH = "finish"

AGENT_ACTION_NAMES = (
    AGENT_ACTION_READ_FILE,
    AGENT_ACTION_SEARCH_REPO,
    AGENT_ACTION_PROPOSE_PATCH,
    AGENT_ACTION_FINISH,
)

AgentLoopStopReason = Literal[
    "proposal_received",
    "finished_without_patch",
    "turn_budget_exhausted",
    "token_budget_exhausted",
    "repeated_state",
    "provider_error",
]

AGENT_LOOP_STOP_REASONS = (
    "proposal_received",
    "finished_without_patch",
    "turn_budget_exhausted",
    "token_budget_exhausted",
    "repeated_state",
    "provider_error",
)


@dataclass(frozen=True)
class AgentToolLoopRequest:
    task_id: str
    query: str
    intent: str
    expected_behavior: str
    verification_summary: str
    seed_evidence: tuple[EditProposalEvidenceContext, ...] = ()
    seed_target_file: str | None = None
    allowed_file_paths: tuple[str, ...] = ()
    repair_context: str = ""
    proposal_mode: str = "unified_diff"
    max_turns: int = 10
    max_total_tokens_in: int | None = None
    max_total_tokens_out: int | None = None


@dataclass(frozen=True)
class AgentToolObservation:
    ok: bool
    content: str
    error_code: str | None = None
    truncated: bool = False


@dataclass(frozen=True)
class AgentLoopTurn:
    turn_index: int
    action_name: str
    arguments_summary: dict[str, object] = field(default_factory=dict)
    observation_ok: bool = True
    observation_error_code: str | None = None
    observation_chars: int = 0
    repeated_warning: bool = False
    prompt_chars: int = 0
    response_chars: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = "unknown"
    finish_reason: str | None = None
    response_excerpt: str = ""


@dataclass(frozen=True)
class AgentProposal:
    target_file: str
    diff: str
    rationale: str
    evidence_ids: tuple[str, ...] = ()
    risk_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentToolLoopResult:
    stop_reason: AgentLoopStopReason
    turns: tuple[AgentLoopTurn, ...] = ()
    error_code: str | None = None
    error_message: str | None = None
    proposal: AgentProposal | None = None
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    repeated_action_count: int = 0
