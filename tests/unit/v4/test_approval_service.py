from homllm_v4.contracts.approval import ApprovalDecision, ApprovalRequest
from homllm_v4.services.approval_service import ApprovalRegistry
from homllm_v4.services.approval_store import ApprovalStore


def request(
    *,
    request_id: str = "approval-1",
    task_id: str = "task-1",
    session_id: str = "session-1",
    subject: str = "python.exe",
) -> ApprovalRequest:
    return ApprovalRequest(
        request_id=request_id,
        task_id=task_id,
        session_id=session_id,
        requested_capability="command_execution",
        subject=subject,
        reason="run verification",
    )


def decision(
    *,
    request_id: str = "approval-1",
    approved: bool = True,
    scope: str = "once",
) -> ApprovalDecision:
    return ApprovalDecision(
        request_id=request_id,
        approved=approved,
        scope=scope,
        approver="test",
    )


def test_once_approval_is_consumed_after_first_use() -> None:
    registry = ApprovalRegistry()
    registry.record(request(), decision(scope="once"))

    assert registry.is_approved(
        task_id="task-1",
        session_id="session-1",
        requested_capability="command_execution",
        subject="python.exe",
    )
    assert not registry.is_approved(
        task_id="task-1",
        session_id="session-1",
        requested_capability="command_execution",
        subject="python.exe",
    )


def test_task_approval_only_matches_same_task() -> None:
    registry = ApprovalRegistry()
    registry.record(request(), decision(scope="task"))

    assert registry.is_approved(
        task_id="task-1",
        session_id="session-1",
        requested_capability="command_execution",
        subject="python.exe",
    )
    assert not registry.is_approved(
        task_id="task-2",
        session_id="session-1",
        requested_capability="command_execution",
        subject="python.exe",
    )


def test_session_approval_matches_tasks_in_same_session() -> None:
    registry = ApprovalRegistry()
    registry.record(request(), decision(scope="session"))

    assert registry.is_approved(
        task_id="task-2",
        session_id="session-1",
        requested_capability="command_execution",
        subject="python.exe",
    )
    assert not registry.is_approved(
        task_id="task-1",
        session_id="session-2",
        requested_capability="command_execution",
        subject="python.exe",
    )


def test_denied_decision_does_not_approve() -> None:
    registry = ApprovalRegistry()
    registry.record(request(), decision(approved=False, scope="session"))

    assert not registry.is_approved(
        task_id="task-1",
        session_id="session-1",
        requested_capability="command_execution",
        subject="python.exe",
    )


def test_approval_store_persists_and_replays_registry(tmp_path) -> None:
    path = tmp_path / "approvals.jsonl"
    store = ApprovalStore(path)
    store.append(request(), decision(scope="task"))

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    registry = store.load_registry()

    assert registry.is_approved(
        task_id="task-1",
        session_id="session-1",
        requested_capability="command_execution",
        subject="python.exe",
    )


def test_approval_store_rejects_corrupt_records(tmp_path) -> None:
    path = tmp_path / "approvals.jsonl"
    path.write_text("[]\n", encoding="utf-8")
    store = ApprovalStore(path)

    try:
        store.load_registry()
    except ValueError as exc:
        assert str(exc) == "approval_store_corrupt"
    else:
        raise AssertionError("expected approval_store_corrupt")
