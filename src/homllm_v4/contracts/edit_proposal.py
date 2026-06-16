from dataclasses import dataclass


@dataclass(frozen=True)
class EditProposalEvidenceContext:
    evidence_id: str
    file_path: str
    span_start: int | None
    span_end: int | None
    content: str


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


@dataclass(frozen=True)
class EditProposalResult:
    target_file: str
    new_content: str
    rationale: str
    evidence_ids: tuple[str, ...]
    risk_flags: tuple[str, ...]
