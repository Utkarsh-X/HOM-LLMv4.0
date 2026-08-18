from dataclasses import dataclass


@dataclass(frozen=True)
class EditProposalEvidenceContext:
    evidence_id: str
    file_path: str
    span_start: int | None
    span_end: int | None
    content: str


PROPOSAL_MODE_FULL_CONTENT = "full_content"
PROPOSAL_MODE_UNIFIED_DIFF = "unified_diff"

PROPOSAL_MODES = (PROPOSAL_MODE_FULL_CONTENT, PROPOSAL_MODE_UNIFIED_DIFF)


def validate_proposal_mode(mode: str) -> str:
    if mode not in PROPOSAL_MODES:
        raise ValueError(f"unsupported_proposal_mode: {mode}")
    return mode


@dataclass(frozen=True)
class EditProposalRequest:
    task_id: str
    target_file: str
    intent: str
    expected_behavior: str
    current_content: str
    evidence_ids: tuple[str, ...]
    allowed_file_paths: tuple[str, ...]
    verification_summary: str
    evidence_context: tuple[EditProposalEvidenceContext, ...] = ()
    repair_context: str = ""
    proposal_mode: str = PROPOSAL_MODE_FULL_CONTENT


@dataclass(frozen=True)
class EditProposalResult:
    target_file: str
    new_content: str
    rationale: str
    evidence_ids: tuple[str, ...]
    risk_flags: tuple[str, ...]
    diff: str | None = None
