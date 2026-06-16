from dataclasses import dataclass

from homllm_v4.contracts.approval import ApprovalDecision, ApprovalRequest, ApprovalScope


@dataclass
class _ApprovalGrant:
    request: ApprovalRequest
    decision: ApprovalDecision
    consumed: bool = False


class ApprovalRegistry:
    def __init__(self) -> None:
        self._grants: list[_ApprovalGrant] = []

    def record(self, request: ApprovalRequest, decision: ApprovalDecision) -> None:
        if request.request_id != decision.request_id:
            raise ValueError("approval request_id mismatch")
        self._grants.append(_ApprovalGrant(request=request, decision=decision))

    def is_approved(
        self,
        *,
        task_id: str,
        session_id: str,
        requested_capability: str,
        subject: str,
    ) -> bool:
        for grant in self._grants:
            if not self._matches(
                grant,
                task_id=task_id,
                session_id=session_id,
                requested_capability=requested_capability,
                subject=subject,
            ):
                continue
            if grant.decision.scope == "once":
                grant.consumed = True
            return True
        return False

    @staticmethod
    def _matches(
        grant: _ApprovalGrant,
        *,
        task_id: str,
        session_id: str,
        requested_capability: str,
        subject: str,
    ) -> bool:
        if not grant.decision.approved or grant.consumed:
            return False
        request = grant.request
        if request.requested_capability != requested_capability:
            return False
        if request.subject != subject:
            return False
        return _scope_matches(
            grant.decision.scope,
            request_task_id=request.task_id,
            request_session_id=request.session_id,
            task_id=task_id,
            session_id=session_id,
        )


def _scope_matches(
    scope: ApprovalScope,
    *,
    request_task_id: str,
    request_session_id: str,
    task_id: str,
    session_id: str,
) -> bool:
    if scope == "once":
        return request_task_id == task_id and request_session_id == session_id
    if scope == "task":
        return request_task_id == task_id
    if scope == "session":
        return request_session_id == session_id
    return False
