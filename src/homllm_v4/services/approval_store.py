import json
from pathlib import Path

from homllm_v4.contracts.approval import ApprovalDecision, ApprovalRequest
from homllm_v4.serialization.json import to_jsonable
from homllm_v4.services.approval_service import ApprovalRegistry


class ApprovalStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def append(self, request: ApprovalRequest, decision: ApprovalDecision) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            to_jsonable(
                {
                    "request": request,
                    "decision": decision,
                }
            ),
            sort_keys=True,
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
            handle.flush()

    def load_registry(self) -> ApprovalRegistry:
        registry = ApprovalRegistry()
        if not self.path.exists():
            return registry
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                request = _request_from_record(record)
                decision = _decision_from_record(record)
                registry.record(request, decision)
        except Exception as exc:
            raise ValueError("approval_store_corrupt") from exc
        return registry


def _request_from_record(record: object) -> ApprovalRequest:
    if not isinstance(record, dict):
        raise ValueError("approval record must be an object")
    request = record.get("request")
    if not isinstance(request, dict):
        raise ValueError("approval request must be an object")
    return ApprovalRequest(
        request_id=_str_field(request, "request_id"),
        task_id=_str_field(request, "task_id"),
        session_id=_str_field(request, "session_id"),
        requested_capability=_str_field(request, "requested_capability"),
        subject=_str_field(request, "subject"),
        reason=_str_field(request, "reason"),
    )


def _decision_from_record(record: object) -> ApprovalDecision:
    if not isinstance(record, dict):
        raise ValueError("approval record must be an object")
    decision = record.get("decision")
    if not isinstance(decision, dict):
        raise ValueError("approval decision must be an object")
    scope = _str_field(decision, "scope")
    if scope not in {"once", "task", "session"}:
        raise ValueError("invalid approval scope")
    approved = decision.get("approved")
    if not isinstance(approved, bool):
        raise ValueError("approval approved must be a bool")
    return ApprovalDecision(
        request_id=_str_field(decision, "request_id"),
        approved=approved,
        scope=scope,
        approver=_str_field(decision, "approver"),
    )


def _str_field(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"missing string field: {key}")
    return value
