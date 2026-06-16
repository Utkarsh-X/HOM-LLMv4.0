from dataclasses import dataclass
from typing import Literal

ApprovalScope = Literal["once", "task", "session"]


@dataclass(frozen=True)
class ApprovalRequest:
    request_id: str
    task_id: str
    session_id: str
    requested_capability: str
    subject: str
    reason: str


@dataclass(frozen=True)
class ApprovalDecision:
    request_id: str
    approved: bool
    scope: ApprovalScope
    approver: str
