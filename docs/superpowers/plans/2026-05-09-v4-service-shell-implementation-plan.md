# v4 Service Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the HOM-LLM v4 Milestone 1 service shell: typed contracts, serialization, artifacts, event ledger, registry, direct read service, index validation shell, adapter boundary enforcement, and a minimal read-only context app with fake-service tests.

**Architecture:** v4 lives beside v3 under `src/homllm_v4/`. Contracts are stable dataclasses; services return `CapabilityResult`; adapters are the only layer allowed to import v3 internals. Milestone 1 proves the shell and boundary discipline without LLM generation, command execution, patching, sandbox backend, or multi-pass agent loop.

**Tech Stack:** Python, frozen dataclasses, pytest, pathlib, json, hashlib, AST import scanning.

---

## Required Reading

Read these before implementing:

- `RULES.md`
- `ENGINEERING_CODEX.md`
- `AI_ENGINEERING_RULES.md`
- `ARCHITECTURE_BOUNDARIES.md`
- `TDD_WORKFLOW.md`
- `docs/v4_architecture/07-milestone-1-implementation-spec.md`

## Implementation Boundary

Do not implement:

- LLM generation
- command execution
- patch tools
- sandbox backend
- approval flow
- multi-pass planner
- sufficiency loop
- product UI

Do not modify v3 orchestration. If a v3 compatibility shim appears necessary, stop and request review.

## File Structure

Create:

```text
src/homllm_v4/
  __init__.py
  app/__init__.py
  app/readonly_context_app.py
  artifacts/__init__.py
  artifacts/manager.py
  contracts/__init__.py
  contracts/artifacts.py
  contracts/capability.py
  contracts/context.py
  contracts/errors.py
  contracts/evidence.py
  contracts/index.py
  contracts/policy.py
  contracts/ranking.py
  contracts/task.py
  contracts/telemetry.py
  ledger/__init__.py
  ledger/events.py
  ledger/writer.py
  registry/__init__.py
  registry/service_registry.py
  services/__init__.py
  services/context_service.py
  services/direct_read_service.py
  services/index_service.py
  services/ranking_service.py
  services/retrieval_service.py
  adapters/__init__.py
  adapters/v3_context_adapter.py
  adapters/v3_index_adapter.py
  adapters/v3_ranking_adapter.py
  adapters/v3_retrieval_adapter.py
  serialization/__init__.py
  serialization/json.py
```

Create:

```text
tests/unit/v4/
  test_artifact_manager.py
  test_capability_result.py
  test_direct_read_service.py
  test_event_writer.py
  test_index_service_contract.py
  test_readonly_context_app_contract.py
  test_service_registry.py
  test_v3_adapter_boundaries.py
```

## Task 1: Contracts And Serialization

**Files:**
- Create: `src/homllm_v4/__init__.py`
- Create: `src/homllm_v4/contracts/__init__.py`
- Create: `src/homllm_v4/contracts/artifacts.py`
- Create: `src/homllm_v4/contracts/capability.py`
- Create: `src/homllm_v4/contracts/context.py`
- Create: `src/homllm_v4/contracts/errors.py`
- Create: `src/homllm_v4/contracts/evidence.py`
- Create: `src/homllm_v4/contracts/index.py`
- Create: `src/homllm_v4/contracts/policy.py`
- Create: `src/homllm_v4/contracts/ranking.py`
- Create: `src/homllm_v4/contracts/task.py`
- Create: `src/homllm_v4/contracts/telemetry.py`
- Create: `src/homllm_v4/serialization/__init__.py`
- Create: `src/homllm_v4/serialization/json.py`
- Test: `tests/unit/v4/test_capability_result.py`

- [ ] **Step 1: Write the failing contract and serialization test**

Create `tests/unit/v4/test_capability_result.py`:

```python
from dataclasses import dataclass
from pathlib import Path

import pytest

from homllm_v4.contracts.artifacts import ArtifactRef
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.serialization.json import to_jsonable


def telemetry(degraded: bool = False) -> CapabilityTelemetry:
    return CapabilityTelemetry(
        started_at="2026-05-09T00:00:00Z",
        ended_at="2026-05-09T00:00:01Z",
        duration_ms=1000,
        input_summary={"query": "hello"},
        output_summary={"count": 1},
        token_usage={},
        model_usage={},
        degraded=degraded,
        degradation_reason="partial vector failure" if degraded else None,
    )


def error() -> CapabilityError:
    return CapabilityError(
        code="adapter_failed",
        message="adapter failed",
        recoverable=False,
        retryable=False,
        details={"stage": "retrieval"},
    )


def test_success_requires_output_and_no_error() -> None:
    result = CapabilityResult(
        capability_name="demo",
        ok=True,
        output={"value": 1},
        error=None,
        telemetry=telemetry(),
        artifacts=(),
    )

    assert result.ok is True
    assert result.output == {"value": 1}


def test_success_without_output_is_invalid() -> None:
    with pytest.raises(ValueError, match="requires output"):
        CapabilityResult(
            capability_name="demo",
            ok=True,
            output=None,
            error=None,
            telemetry=telemetry(),
            artifacts=(),
        )


def test_success_with_error_is_invalid() -> None:
    with pytest.raises(ValueError, match="cannot include error"):
        CapabilityResult(
            capability_name="demo",
            ok=True,
            output={"value": 1},
            error=error(),
            telemetry=telemetry(),
            artifacts=(),
        )


def test_failure_requires_error() -> None:
    with pytest.raises(ValueError, match="requires error"):
        CapabilityResult(
            capability_name="demo",
            ok=False,
            output=None,
            error=None,
            telemetry=telemetry(),
            artifacts=(),
        )


def test_degraded_success_is_representable() -> None:
    result = CapabilityResult(
        capability_name="demo",
        ok=True,
        output={"value": 1},
        error=None,
        telemetry=telemetry(degraded=True),
        artifacts=(),
    )

    assert result.ok is True
    assert result.telemetry.degraded is True
    assert result.telemetry.degradation_reason == "partial vector failure"


def test_serialization_preserves_nested_contract_fields() -> None:
    artifact = ArtifactRef(
        artifact_type="context",
        path="workspace/.homllm/runs/run-1/context/context.json",
        description="context artifact",
        content_hash=None,
    )
    result = CapabilityResult(
        capability_name="demo",
        ok=True,
        output={"path": Path("a/b"), "items": (1, None, True, 1.5, "x")},
        error=None,
        telemetry=telemetry(),
        artifacts=(artifact,),
    )

    payload = to_jsonable(result)

    assert payload["ok"] is True
    assert payload["output"] == {
        "path": "a/b",
        "items": [1, None, True, 1.5, "x"],
    }
    assert payload["artifacts"][0]["content_hash"] is None


def test_unsupported_serialization_type_raises_value_error() -> None:
    @dataclass(frozen=True)
    class UnsupportedContainer:
        value: object

    with pytest.raises(ValueError, match="serialization_failed"):
        to_jsonable(UnsupportedContainer(value=object()))
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_capability_result.py -q
```

Expected:
- Fails with `ModuleNotFoundError: No module named 'homllm_v4'`.

- [ ] **Step 3: Implement the contract modules and serializer**

Create the package directories and files. Implement these exact minimum contracts.

`src/homllm_v4/contracts/errors.py`:

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CapabilityError:
    code: str
    message: str
    recoverable: bool
    retryable: bool
    details: dict[str, object] = field(default_factory=dict)
```

`src/homllm_v4/contracts/artifacts.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactRef:
    artifact_type: str
    path: str
    description: str
    content_hash: str | None
```

`src/homllm_v4/contracts/telemetry.py`:

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CapabilityTelemetry:
    started_at: str
    ended_at: str
    duration_ms: int
    input_summary: dict[str, object] = field(default_factory=dict)
    output_summary: dict[str, object] = field(default_factory=dict)
    token_usage: dict[str, int] = field(default_factory=dict)
    model_usage: dict[str, object] = field(default_factory=dict)
    degraded: bool = False
    degradation_reason: str | None = None
```

`src/homllm_v4/contracts/capability.py`:

```python
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from homllm_v4.contracts.artifacts import ArtifactRef
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.telemetry import CapabilityTelemetry

T = TypeVar("T")


@dataclass(frozen=True)
class CapabilityResult(Generic[T]):
    capability_name: str
    ok: bool
    output: T | None
    error: CapabilityError | None
    telemetry: CapabilityTelemetry
    artifacts: tuple[ArtifactRef, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.ok:
            if self.output is None:
                raise ValueError("successful CapabilityResult requires output")
            if self.error is not None:
                raise ValueError("successful CapabilityResult cannot include error")
        elif self.error is None:
            raise ValueError("failed CapabilityResult requires error")
```

`src/homllm_v4/contracts/policy.py`:

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CapabilityPolicy:
    permission_profile: str
    approval_policy: str
    sandbox_policy: str
    allowed_tools: tuple[str, ...]
    blocked_tools: tuple[str, ...]
    verification_requirements: tuple[str, ...] = field(default_factory=tuple)
    budget_caps: dict[str, int] = field(default_factory=dict)
    escalation_rules: tuple[str, ...] = field(default_factory=tuple)


def read_only_milestone1_policy() -> CapabilityPolicy:
    return CapabilityPolicy(
        permission_profile="ReadOnly",
        approval_policy="never",
        sandbox_policy="read_only",
        allowed_tools=(
            "index.validate",
            "evidence.retrieve",
            "evidence.rank",
            "context.build",
            "file.read",
        ),
        blocked_tools=("command.run", "patch.apply", "tests.run"),
        verification_requirements=(),
        budget_caps={
            "retrieval_calls": 1,
            "ranking_calls": 1,
            "context_calls": 1,
            "direct_reads": 3,
            "llm_calls": 0,
        },
        escalation_rules=(),
    )
```

`src/homllm_v4/serialization/json.py`:

```python
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path


def to_jsonable(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    raise ValueError(f"serialization_failed: unsupported type {type(value).__name__}")


def write_json_file(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_jsonable(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json_file(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("serialization_failed: expected JSON object")
    return data
```

Create empty `__init__.py` files for `src/homllm_v4/`, `contracts/`, and `serialization/`.

Create remaining contract files with minimum dataclasses from later tasks:

`task.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    task_id: str
    user_query: str
    workspace_root: str
    task_class: str
```

`evidence.py`, `ranking.py`, `context.py`, and `index.py` can be created in later tasks when their tests require exact fields.

- [ ] **Step 4: Run the test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_capability_result.py -q
```

Expected:
- All tests in `test_capability_result.py` pass.

- [ ] **Step 5: Run a focused import check**

Run:

```powershell
.\.venv\Scripts\python.exe - <<'PY'
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.policy import read_only_milestone1_policy
print(CapabilityResult.__name__)
print(read_only_milestone1_policy().permission_profile)
PY
```

Expected:
- Prints `CapabilityResult`.
- Prints `ReadOnly`.

- [ ] **Step 6: Checkpoint**

Do not commit unless the user explicitly asks for commits. Record changed files in the session summary.

## Task 2: Artifact Manager

**Files:**
- Create: `src/homllm_v4/artifacts/__init__.py`
- Create: `src/homllm_v4/artifacts/manager.py`
- Test: `tests/unit/v4/test_artifact_manager.py`

- [ ] **Step 1: Write the failing artifact manager test**

Create `tests/unit/v4/test_artifact_manager.py`:

```python
import json
from pathlib import Path

import pytest

from homllm_v4.artifacts.manager import ArtifactManager


def test_create_run_creates_required_layout(tmp_path: Path) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")

    manager.create_run("run-1", {"purpose": "test"})

    run_dir = tmp_path / ".homllm" / "runs" / "run-1"
    assert (run_dir / "metadata.json").is_file()
    assert (run_dir / "task.json").is_file()
    assert (run_dir / "events.jsonl").is_file()
    for name in ("snapshots", "evidence", "context", "commands", "patches", "verification", "response"):
        assert (run_dir / name).is_dir()
    assert json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))["purpose"] == "test"


def test_write_json_returns_artifact_ref_with_stable_hash(tmp_path: Path) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("run-1", {})

    first = manager.write_json("evidence/candidates.json", {"b": 2, "a": 1}, "evidence", "candidate dump")
    second = manager.write_json("evidence/candidates-copy.json", {"b": 2, "a": 1}, "evidence", "candidate dump")

    assert first.artifact_type == "evidence"
    assert first.description == "candidate dump"
    assert first.content_hash == second.content_hash
    assert first.path.endswith(".homllm/runs/run-1/evidence/candidates.json")


def test_write_text_returns_artifact_ref(tmp_path: Path) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("run-1", {})

    artifact = manager.write_text("context/context.txt", "hello", "context", "context text")

    assert artifact.content_hash is not None
    assert (tmp_path / artifact.path).read_text(encoding="utf-8") == "hello"


def test_path_traversal_is_denied(tmp_path: Path) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("run-1", {})

    with pytest.raises(ValueError, match="path_denied"):
        manager.write_text("../escape.txt", "bad", "debug", "bad")
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_artifact_manager.py -q
```

Expected:
- Fails because `homllm_v4.artifacts.manager` does not exist.

- [ ] **Step 3: Implement `ArtifactManager`**

Create `src/homllm_v4/artifacts/manager.py`:

```python
import hashlib
from pathlib import Path

from homllm_v4.contracts.artifacts import ArtifactRef
from homllm_v4.serialization.json import write_json_file


class ArtifactManager:
    def __init__(self, *, workspace_root: Path, artifact_root: Path | None = None) -> None:
        self.workspace_root = workspace_root.resolve()
        self.artifact_root = (artifact_root or self.workspace_root / ".homllm" / "runs").resolve()
        self._run_dir: Path | None = None

    @property
    def run_dir(self) -> Path:
        if self._run_dir is None:
            raise ValueError("artifact_write_failed: run has not been created")
        return self._run_dir

    def create_run(self, run_id: str, metadata: dict[str, object]) -> None:
        self._run_dir = (self.artifact_root / run_id).resolve()
        self._ensure_inside(self._run_dir, self.artifact_root)
        self._run_dir.mkdir(parents=True, exist_ok=True)
        for name in ("snapshots", "evidence", "context", "commands", "patches", "verification", "response"):
            (self._run_dir / name).mkdir(exist_ok=True)
        write_json_file(self._run_dir / "metadata.json", metadata)
        write_json_file(self._run_dir / "task.json", {})
        (self._run_dir / "events.jsonl").touch(exist_ok=True)

    def write_json(self, relative_path: str, payload: object, artifact_type: str, description: str) -> ArtifactRef:
        path = self.resolve_artifact_path(relative_path)
        write_json_file(path, payload)
        return self._artifact_ref(path, artifact_type, description)

    def write_text(self, relative_path: str, text: str, artifact_type: str, description: str) -> ArtifactRef:
        path = self.resolve_artifact_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return self._artifact_ref(path, artifact_type, description)

    def resolve_artifact_path(self, relative_path: str) -> Path:
        candidate = (self.run_dir / relative_path).resolve()
        self._ensure_inside(candidate, self.run_dir)
        return candidate

    def _artifact_ref(self, path: Path, artifact_type: str, description: str) -> ArtifactRef:
        return ArtifactRef(
            artifact_type=artifact_type,
            path=self._display_path(path),
            description=description,
            content_hash=self._sha256_text(path.read_text(encoding="utf-8")),
        )

    def _display_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.workspace_root).as_posix()
        except ValueError:
            return str(path.resolve())

    @staticmethod
    def _sha256_text(text: str) -> str:
        normalized = text.replace("\r\n", "\n").encode("utf-8")
        return hashlib.sha256(normalized).hexdigest()

    @staticmethod
    def _ensure_inside(path: Path, root: Path) -> None:
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"path_denied: {path}") from exc
```

Create `src/homllm_v4/artifacts/__init__.py`.

- [ ] **Step 4: Run the artifact tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_artifact_manager.py -q
```

Expected:
- All artifact manager tests pass.

- [ ] **Step 5: Run contract and artifact tests together**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_capability_result.py tests/unit/v4/test_artifact_manager.py -q
```

Expected:
- Both test files pass.

- [ ] **Step 6: Checkpoint**

Do not commit unless explicitly authorized.

## Task 3: Event Writer And Event Contracts

**Files:**
- Create: `src/homllm_v4/ledger/__init__.py`
- Create: `src/homllm_v4/ledger/events.py`
- Create: `src/homllm_v4/ledger/writer.py`
- Test: `tests/unit/v4/test_event_writer.py`

- [ ] **Step 1: Write the failing event writer test**

Create `tests/unit/v4/test_event_writer.py`:

```python
import json
from pathlib import Path

from homllm_v4.contracts.artifacts import ArtifactRef
from homllm_v4.ledger.events import RunEvent
from homllm_v4.ledger.writer import EventWriter


def event(event_type: str, artifact_refs: tuple[ArtifactRef, ...] = ()) -> RunEvent:
    return RunEvent(
        event_id=f"event-{event_type}",
        run_id="run-1",
        task_id="task-1",
        phase="test",
        event_type=event_type,
        timestamp="2026-05-09T00:00:00Z",
        summary={"ok": True},
        artifact_refs=artifact_refs,
    )


def test_event_writer_appends_json_lines_in_order(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    writer = EventWriter(path)

    writer.append(event("run_started"))
    writer.append(event("run_completed"))

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event_type"] == "run_started"
    assert json.loads(lines[1])["event_type"] == "run_completed"


def test_event_writer_serializes_artifact_refs(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    writer = EventWriter(path)
    artifact = ArtifactRef("context", ".homllm/runs/run-1/context/a.json", "context", "abc")

    writer.append(event("context_completed", (artifact,)))

    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert payload["artifact_refs"][0]["artifact_type"] == "context"
    assert payload["artifact_refs"][0]["content_hash"] == "abc"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_event_writer.py -q
```

Expected:
- Fails because `homllm_v4.ledger.events` or `writer` does not exist.

- [ ] **Step 3: Implement `RunEvent`, event constants, and `EventWriter`**

Create `src/homllm_v4/ledger/events.py`:

```python
from dataclasses import dataclass, field

from homllm_v4.contracts.artifacts import ArtifactRef

RUN_STARTED = "run_started"
POLICY_CREATED = "policy_created"
ARTIFACT_WRITTEN = "artifact_written"
INDEX_VALIDATED = "index_validated"
RETRIEVAL_COMPLETED = "retrieval_completed"
RANKING_COMPLETED = "ranking_completed"
CONTEXT_COMPLETED = "context_completed"
SERVICE_FAILED = "service_failed"
RUN_COMPLETED = "run_completed"


@dataclass(frozen=True)
class RunEvent:
    event_id: str
    run_id: str
    task_id: str
    phase: str
    event_type: str
    timestamp: str
    summary: dict[str, object] = field(default_factory=dict)
    artifact_refs: tuple[ArtifactRef, ...] = field(default_factory=tuple)
```

Create `src/homllm_v4/ledger/writer.py`:

```python
import json
from pathlib import Path

from homllm_v4.ledger.events import RunEvent
from homllm_v4.serialization.json import to_jsonable


class EventWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: RunEvent) -> None:
        payload = json.dumps(to_jsonable(event), sort_keys=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
            handle.flush()
```

Create `src/homllm_v4/ledger/__init__.py`.

- [ ] **Step 4: Run event writer tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_event_writer.py -q
```

Expected:
- All event writer tests pass.

- [ ] **Step 5: Run current v4 unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4 -q
```

Expected:
- Current implemented v4 tests pass.

- [ ] **Step 6: Checkpoint**

Do not commit unless explicitly authorized.

## Task 4: Service Registry

**Files:**
- Create: `src/homllm_v4/registry/__init__.py`
- Create: `src/homllm_v4/registry/service_registry.py`
- Test: `tests/unit/v4/test_service_registry.py`

- [ ] **Step 1: Write the failing service registry test**

Create `tests/unit/v4/test_service_registry.py`:

```python
import pytest

from homllm_v4.registry.service_registry import ServiceRegistry


class DemoService:
    pass


class OtherService:
    pass


def test_register_and_get_typed_service() -> None:
    registry = ServiceRegistry()
    service = DemoService()

    registry.register("demo", service)

    assert registry.get("demo", DemoService) is service
    assert registry.names() == ("demo",)


def test_duplicate_registration_fails() -> None:
    registry = ServiceRegistry()
    registry.register("demo", DemoService())

    with pytest.raises(ValueError, match="service_already_registered"):
        registry.register("demo", DemoService())


def test_missing_lookup_fails() -> None:
    registry = ServiceRegistry()

    with pytest.raises(ValueError, match="service_not_registered"):
        registry.get("missing", DemoService)


def test_wrong_expected_type_fails() -> None:
    registry = ServiceRegistry()
    registry.register("demo", DemoService())

    with pytest.raises(TypeError, match="service_type_mismatch"):
        registry.get("demo", OtherService)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_service_registry.py -q
```

Expected:
- Fails because registry module does not exist.

- [ ] **Step 3: Implement `ServiceRegistry`**

Create `src/homllm_v4/registry/service_registry.py`:

```python
from typing import TypeVar

T = TypeVar("T")


class ServiceRegistry:
    def __init__(self) -> None:
        self._services: dict[str, object] = {}

    def register(self, name: str, service: object) -> None:
        if name in self._services:
            raise ValueError(f"service_already_registered: {name}")
        self._services[name] = service

    def get(self, name: str, expected_type: type[T]) -> T:
        if name not in self._services:
            raise ValueError(f"service_not_registered: {name}")
        service = self._services[name]
        if not isinstance(service, expected_type):
            raise TypeError(
                f"service_type_mismatch: {name} expected {expected_type.__name__} got {type(service).__name__}"
            )
        return service

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._services))
```

Create `src/homllm_v4/registry/__init__.py`.

- [ ] **Step 4: Run service registry tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_service_registry.py -q
```

Expected:
- All service registry tests pass.

- [ ] **Step 5: Run current v4 unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4 -q
```

Expected:
- Current implemented v4 tests pass.

- [ ] **Step 6: Checkpoint**

Do not commit unless explicitly authorized.

## Task 5: Direct Read Service

**Files:**
- Create: `src/homllm_v4/services/__init__.py`
- Create: `src/homllm_v4/services/direct_read_service.py`
- Add exact dataclasses to: `src/homllm_v4/contracts/evidence.py`
- Test: `tests/unit/v4/test_direct_read_service.py`

- [ ] **Step 1: Write the failing direct read service test**

Create `tests/unit/v4/test_direct_read_service.py`:

```python
from pathlib import Path

import pytest

from homllm_v4.contracts.evidence import DirectReadRequest
from homllm_v4.services.direct_read_service import DirectReadService


def test_reads_workspace_file_with_hash(tmp_path: Path) -> None:
    target = tmp_path / "src" / "demo.py"
    target.parent.mkdir()
    target.write_text("line1\nline2\nline3\n", encoding="utf-8")
    service = DirectReadService(workspace_root=tmp_path)

    result = service.read(DirectReadRequest(task_id="task-1", file_path="src/demo.py"))

    assert result.ok is True
    assert result.output is not None
    assert result.output.content_excerpt == "line1\nline2\nline3\n"
    assert result.output.content_hash is not None
    assert result.output.freshness == "fresh"


def test_line_slicing_is_one_based_and_inclusive(tmp_path: Path) -> None:
    target = tmp_path / "src" / "demo.py"
    target.parent.mkdir()
    target.write_text("line1\nline2\nline3\n", encoding="utf-8")
    service = DirectReadService(workspace_root=tmp_path)

    result = service.read(
        DirectReadRequest(
            task_id="task-1",
            file_path="src/demo.py",
            line_start=2,
            line_end=3,
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.content_excerpt == "line2\nline3\n"


def test_path_outside_workspace_is_denied(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    service = DirectReadService(workspace_root=tmp_path)

    result = service.read(DirectReadRequest(task_id="task-1", file_path="../outside.txt"))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "path_denied"


def test_large_file_limit_is_enforced(tmp_path: Path) -> None:
    target = tmp_path / "large.txt"
    target.write_text("abcdef", encoding="utf-8")
    service = DirectReadService(workspace_root=tmp_path)

    result = service.read(DirectReadRequest(task_id="task-1", file_path="large.txt", max_bytes=3))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "file_too_large"


def test_missing_file_returns_structured_error(tmp_path: Path) -> None:
    service = DirectReadService(workspace_root=tmp_path)

    result = service.read(DirectReadRequest(task_id="task-1", file_path="missing.py"))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "file_not_found"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_direct_read_service.py -q
```

Expected:
- Fails because direct read contracts/service do not exist.

- [ ] **Step 3: Implement direct read contracts**

Create or update `src/homllm_v4/contracts/evidence.py`:

```python
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DirectReadRequest:
    task_id: str
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    max_bytes: int = 20000
    require_hash: bool = True


@dataclass(frozen=True)
class DirectReadResult:
    file_path: str
    content_excerpt: str
    line_start: int | None
    line_end: int | None
    content_hash: str | None
    truncated: bool
    freshness: Literal["fresh", "possibly_stale", "stale"]
```

- [ ] **Step 4: Implement `DirectReadService`**

Create `src/homllm_v4/services/direct_read_service.py`:

```python
import hashlib
from pathlib import Path
from time import perf_counter

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import DirectReadRequest, DirectReadResult
from homllm_v4.contracts.telemetry import CapabilityTelemetry


class DirectReadService:
    def __init__(self, *, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()

    def read(self, request: DirectReadRequest) -> CapabilityResult[DirectReadResult]:
        started = perf_counter()
        try:
            path = (self.workspace_root / request.file_path).resolve()
            try:
                path.relative_to(self.workspace_root)
            except ValueError:
                return self._failure("path_denied", "path is outside workspace", request, started)
            if not path.exists():
                return self._failure("file_not_found", "file does not exist", request, started)
            if not path.is_file():
                return self._failure("file_not_found", "path is not a file", request, started)
            size = path.stat().st_size
            if size > request.max_bytes:
                return self._failure("file_too_large", "file exceeds max_bytes", request, started, {"size": size})
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return self._failure("binary_file_denied", "file is not utf-8 text", request, started)
            excerpt = self._slice_lines(text, request.line_start, request.line_end)
            output = DirectReadResult(
                file_path=request.file_path,
                content_excerpt=excerpt,
                line_start=request.line_start,
                line_end=request.line_end,
                content_hash=self._hash(text) if request.require_hash else None,
                truncated=False,
                freshness="fresh",
            )
            return CapabilityResult(
                capability_name="file.read",
                ok=True,
                output=output,
                error=None,
                telemetry=self._telemetry(request, started, {"bytes": len(text.encode("utf-8"))}),
                artifacts=(),
            )
        except OSError as exc:
            return self._failure("read_failed", str(exc), request, started)

    def _failure(
        self,
        code: str,
        message: str,
        request: DirectReadRequest,
        started: float,
        details: dict[str, object] | None = None,
    ) -> CapabilityResult[DirectReadResult]:
        return CapabilityResult(
            capability_name="file.read",
            ok=False,
            output=None,
            error=CapabilityError(code=code, message=message, recoverable=False, retryable=False, details=details or {}),
            telemetry=self._telemetry(request, started, {}),
            artifacts=(),
        )

    def _telemetry(self, request: DirectReadRequest, started: float, output_summary: dict[str, object]) -> CapabilityTelemetry:
        duration_ms = int((perf_counter() - started) * 1000)
        return CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=duration_ms,
            input_summary={"file_path": request.file_path, "max_bytes": request.max_bytes},
            output_summary=output_summary,
            token_usage={},
            model_usage={},
            degraded=False,
            degradation_reason=None,
        )

    @staticmethod
    def _slice_lines(text: str, line_start: int | None, line_end: int | None) -> str:
        if line_start is None and line_end is None:
            return text
        lines = text.splitlines(keepends=True)
        start = max((line_start or 1) - 1, 0)
        end = line_end if line_end is not None else len(lines)
        return "".join(lines[start:end])

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()
```

Create `src/homllm_v4/services/__init__.py`.

- [ ] **Step 5: Run direct read tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_direct_read_service.py -q
```

Expected:
- All direct read service tests pass.

- [ ] **Step 6: Run current v4 unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4 -q
```

Expected:
- Current implemented v4 tests pass.

- [ ] **Step 7: Checkpoint**

Do not commit unless explicitly authorized.

## Task 6: Index Service Shell

**Files:**
- Create: `src/homllm_v4/contracts/index.py`
- Create: `src/homllm_v4/services/index_service.py`
- Create: `src/homllm_v4/adapters/__init__.py`
- Create: `src/homllm_v4/adapters/v3_index_adapter.py`
- Test: `tests/unit/v4/test_index_service_contract.py`

- [ ] **Step 1: Write the failing index service contract test**

Create `tests/unit/v4/test_index_service_contract.py`:

```python
from pathlib import Path

from homllm_v4.contracts.index import IndexRequest
from homllm_v4.services.index_service import IndexService


def test_missing_index_artifacts_return_index_missing(tmp_path: Path) -> None:
    service = IndexService()

    result = service.validate(
        IndexRequest(
            workspace_root=str(tmp_path),
            include_patterns=("**/*.py",),
            exclude_patterns=(".git/**",),
            language_profile="python",
            mode="validate",
            artifact_paths={"duckdb": str(tmp_path / "missing.duckdb")},
        )
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "index_missing"


def test_present_artifact_paths_produce_manifest(tmp_path: Path) -> None:
    duckdb = tmp_path / "index.duckdb"
    bm25 = tmp_path / "bm25"
    vector = tmp_path / "vectors"
    duckdb.write_text("fake", encoding="utf-8")
    bm25.mkdir()
    vector.mkdir()
    service = IndexService()

    result = service.validate(
        IndexRequest(
            workspace_root=str(tmp_path),
            include_patterns=("**/*.py",),
            exclude_patterns=(".git/**",),
            language_profile="python",
            mode="validate",
            artifact_paths={
                "duckdb": str(duckdb),
                "bm25": str(bm25),
                "vector": str(vector),
            },
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.manifest.workspace_root == str(tmp_path)
    assert result.output.manifest.artifact_paths["duckdb"] == str(duckdb)
    assert result.output.freshness.status in {"fresh", "possibly_stale"}


def test_validate_mode_does_not_rebuild_index(tmp_path: Path) -> None:
    service = IndexService()

    result = service.validate(
        IndexRequest(
            workspace_root=str(tmp_path),
            include_patterns=("**/*.py",),
            exclude_patterns=(),
            language_profile="python",
            mode="validate",
            artifact_paths={},
        )
    )

    assert result.ok is False
    assert not any(tmp_path.glob("*.duckdb"))
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_index_service_contract.py -q
```

Expected:
- Fails because index contracts/service do not exist.

- [ ] **Step 3: Implement index contracts**

Create `src/homllm_v4/contracts/index.py`:

```python
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class IndexRequest:
    workspace_root: str
    include_patterns: tuple[str, ...]
    exclude_patterns: tuple[str, ...]
    language_profile: str
    mode: Literal["load", "validate", "rebuild", "incremental"]
    artifact_paths: dict[str, str] = field(default_factory=dict)
    max_index_age_seconds: int | None = None
    force: bool = False


@dataclass(frozen=True)
class RepoIndexManifest:
    index_id: str
    workspace_root: str
    schema_version: str
    created_at: str
    last_indexed_at: str
    source_file_count: int
    chunk_count: int
    symbol_count: int
    relation_count: int
    embedding_model: str
    embedding_dimension: int
    artifact_paths: dict[str, str]
    ignored_paths_summary: dict[str, int]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class IndexFreshness:
    status: Literal["fresh", "possibly_stale", "stale"]
    reason: str | None
    indexed_at: str
    workspace_changed_since_index: bool
    stale_file_count: int
    untracked_file_count: int


@dataclass(frozen=True)
class IndexValidation:
    manifest: RepoIndexManifest
    freshness: IndexFreshness
```

- [ ] **Step 4: Implement index adapter shell and service**

Create `src/homllm_v4/adapters/v3_index_adapter.py`:

```python
from pathlib import Path

from homllm_v4.contracts.index import IndexFreshness, IndexRequest, IndexValidation, RepoIndexManifest


class V3IndexAdapter:
    def validate(self, request: IndexRequest) -> IndexValidation:
        artifact_paths = {name: str(Path(path)) for name, path in request.artifact_paths.items()}
        existing = [Path(path) for path in artifact_paths.values() if Path(path).exists()]
        latest_mtime = max((path.stat().st_mtime for path in existing), default=0.0)
        indexed_at = str(latest_mtime)
        manifest = RepoIndexManifest(
            index_id="v3-adapter-index",
            workspace_root=request.workspace_root,
            schema_version="unknown",
            created_at=indexed_at,
            last_indexed_at=indexed_at,
            source_file_count=0,
            chunk_count=0,
            symbol_count=0,
            relation_count=0,
            embedding_model="unknown",
            embedding_dimension=0,
            artifact_paths=artifact_paths,
            ignored_paths_summary={},
            warnings=(),
        )
        freshness = IndexFreshness(
            status="fresh",
            reason=None,
            indexed_at=indexed_at,
            workspace_changed_since_index=False,
            stale_file_count=0,
            untracked_file_count=0,
        )
        return IndexValidation(manifest=manifest, freshness=freshness)
```

Create `src/homllm_v4/services/index_service.py`:

```python
from pathlib import Path
from time import perf_counter

from homllm_v4.adapters.v3_index_adapter import V3IndexAdapter
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.index import IndexRequest, IndexValidation
from homllm_v4.contracts.telemetry import CapabilityTelemetry


class IndexService:
    def __init__(self, adapter: V3IndexAdapter | None = None) -> None:
        self.adapter = adapter or V3IndexAdapter()

    def validate(self, request: IndexRequest) -> CapabilityResult[IndexValidation]:
        started = perf_counter()
        missing = [path for path in request.artifact_paths.values() if not Path(path).exists()]
        if missing:
            return CapabilityResult(
                capability_name="index.validate",
                ok=False,
                output=None,
                error=CapabilityError(
                    code="index_missing",
                    message="one or more index artifacts are missing",
                    recoverable=True,
                    retryable=False,
                    details={"missing": missing},
                ),
                telemetry=self._telemetry(request, started, {"missing": len(missing)}),
                artifacts=(),
            )
        if not request.artifact_paths:
            return CapabilityResult(
                capability_name="index.validate",
                ok=False,
                output=None,
                error=CapabilityError(
                    code="index_missing",
                    message="no index artifact paths were provided",
                    recoverable=True,
                    retryable=False,
                    details={},
                ),
                telemetry=self._telemetry(request, started, {"missing": 0}),
                artifacts=(),
            )
        validation = self.adapter.validate(request)
        return CapabilityResult(
            capability_name="index.validate",
            ok=True,
            output=validation,
            error=None,
            telemetry=self._telemetry(request, started, {"artifact_count": len(request.artifact_paths)}),
            artifacts=(),
        )

    @staticmethod
    def _telemetry(request: IndexRequest, started: float, output_summary: dict[str, object]) -> CapabilityTelemetry:
        return CapabilityTelemetry(
            started_at="",
            ended_at="",
            duration_ms=int((perf_counter() - started) * 1000),
            input_summary={"workspace_root": request.workspace_root, "mode": request.mode},
            output_summary=output_summary,
            token_usage={},
            model_usage={},
            degraded=False,
            degradation_reason=None,
        )
```

Create `src/homllm_v4/adapters/__init__.py`.

- [ ] **Step 5: Run index service tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_index_service_contract.py -q
```

Expected:
- All index service contract tests pass.

- [ ] **Step 6: Run current v4 unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4 -q
```

Expected:
- Current implemented v4 tests pass.

- [ ] **Step 7: Checkpoint**

Do not commit unless explicitly authorized.

## Task 7: AST Import Boundary Tests And Adapter Shells

**Files:**
- Create: `src/homllm_v4/adapters/v3_retrieval_adapter.py`
- Create: `src/homllm_v4/adapters/v3_ranking_adapter.py`
- Create: `src/homllm_v4/adapters/v3_context_adapter.py`
- Test: `tests/unit/v4/test_v3_adapter_boundaries.py`

- [ ] **Step 1: Write the failing AST boundary test**

Create `tests/unit/v4/test_v3_adapter_boundaries.py`:

```python
import ast
from pathlib import Path

FORBIDDEN_PREFIXES = (
    "homllm.retrieval",
    "homllm.ranking",
    "homllm.context",
    "homllm.indexer",
)

SCANNED_DIRS = (
    "services",
    "contracts",
    "registry",
    "ledger",
    "artifacts",
    "serialization",
    "app",
)


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_v3_imports_are_forbidden_outside_adapters() -> None:
    root = Path("src/homllm_v4")
    violations: list[str] = []
    for dirname in SCANNED_DIRS:
        for path in (root / dirname).rglob("*.py"):
            for module in imported_modules(path):
                if module.startswith(FORBIDDEN_PREFIXES):
                    violations.append(f"{path}: {module}")

    assert violations == []


def test_adapter_shells_are_present() -> None:
    root = Path("src/homllm_v4/adapters")

    assert (root / "v3_index_adapter.py").is_file()
    assert (root / "v3_retrieval_adapter.py").is_file()
    assert (root / "v3_ranking_adapter.py").is_file()
    assert (root / "v3_context_adapter.py").is_file()
```

- [ ] **Step 2: Run the boundary test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_v3_adapter_boundaries.py -q
```

Expected:
- Fails because retrieval/ranking/context adapter shell files do not exist.

- [ ] **Step 3: Add adapter shell files**

Create `src/homllm_v4/adapters/v3_retrieval_adapter.py`:

```python
class V3RetrievalAdapter:
    """Compatibility boundary for homllm.retrieval.

    Milestone 1 service tests use fakes. Real v3 translation is added only after
    boundary tests are in place.
    """
```

Create `src/homllm_v4/adapters/v3_ranking_adapter.py`:

```python
class V3RankingAdapter:
    """Compatibility boundary for homllm.ranking."""
```

Create `src/homllm_v4/adapters/v3_context_adapter.py`:

```python
class V3ContextAdapter:
    """Compatibility boundary for homllm.context."""
```

- [ ] **Step 4: Run boundary tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_v3_adapter_boundaries.py -q
```

Expected:
- Boundary tests pass.

- [ ] **Step 5: Run current v4 unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4 -q
```

Expected:
- Current implemented v4 tests pass.

- [ ] **Step 6: Checkpoint**

Do not commit unless explicitly authorized.

## Task 8: Readonly Context App With Fake Services

**Files:**
- Create: `src/homllm_v4/app/__init__.py`
- Create: `src/homllm_v4/app/readonly_context_app.py`
- Create/update: `src/homllm_v4/contracts/context.py`
- Create/update: `src/homllm_v4/contracts/ranking.py`
- Create/update: `src/homllm_v4/contracts/evidence.py`
- Create: `src/homllm_v4/services/retrieval_service.py`
- Create: `src/homllm_v4/services/ranking_service.py`
- Create: `src/homllm_v4/services/context_service.py`
- Test: `tests/unit/v4/test_readonly_context_app_contract.py`

- [ ] **Step 1: Write the failing readonly context app test**

Create `tests/unit/v4/test_readonly_context_app_contract.py`:

```python
from pathlib import Path

from homllm_v4.app.readonly_context_app import build_readonly_context
from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.context import ContextBlock, ContextPack
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import EvidenceCandidate, EvidenceSet, RetrievalDiagnostics
from homllm_v4.contracts.index import IndexFreshness, IndexValidation, RepoIndexManifest
from homllm_v4.contracts.policy import read_only_milestone1_policy
from homllm_v4.contracts.ranking import RankedEvidence, RankedEvidenceSet, RankingDiagnostics
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.registry.service_registry import ServiceRegistry
from homllm_v4.services.context_service import ContextPackService
from homllm_v4.services.index_service import IndexService
from homllm_v4.services.ranking_service import EvidenceRankingService
from homllm_v4.services.retrieval_service import EvidenceRetrievalService


def telemetry() -> CapabilityTelemetry:
    return CapabilityTelemetry(
        started_at="",
        ended_at="",
        duration_ms=1,
        input_summary={},
        output_summary={},
        token_usage={},
        model_usage={},
        degraded=False,
        degradation_reason=None,
    )


class FakeIndexService(IndexService):
    def validate(self, request):
        manifest = RepoIndexManifest(
            index_id="idx",
            workspace_root=request.workspace_root,
            schema_version="test",
            created_at="0",
            last_indexed_at="0",
            source_file_count=1,
            chunk_count=1,
            symbol_count=0,
            relation_count=0,
            embedding_model="none",
            embedding_dimension=0,
            artifact_paths={},
            ignored_paths_summary={},
            warnings=(),
        )
        freshness = IndexFreshness("fresh", None, "0", False, 0, 0)
        return CapabilityResult("index.validate", True, IndexValidation(manifest, freshness), None, telemetry(), ())


class FailingIndexService(IndexService):
    def validate(self, request):
        return CapabilityResult(
            "index.validate",
            False,
            None,
            CapabilityError("index_missing", "missing", True, False, {}),
            telemetry(),
            (),
        )


class FakeRetrievalService(EvidenceRetrievalService):
    def retrieve(self, request):
        candidate = EvidenceCandidate(
            candidate_id="c1",
            file_path="src/demo.py",
            symbol_id=None,
            span_start=1,
            span_end=1,
            content_hash="hash",
            source_channels=("bm25",),
            bm25_score=1.0,
            vector_score=None,
            graph_score=None,
            retrieval_score=1.0,
            metadata={},
        )
        diagnostics = RetrievalDiagnostics(1, 0, 0, 0, 0, None, False, None)
        return CapabilityResult("evidence.retrieve", True, EvidenceSet("es1", request.query, (candidate,), diagnostics), None, telemetry(), ())


class EmptyRetrievalService(EvidenceRetrievalService):
    def retrieve(self, request):
        diagnostics = RetrievalDiagnostics(0, 0, 0, 0, 0, None, False, None)
        return CapabilityResult("evidence.retrieve", True, EvidenceSet("es1", request.query, (), diagnostics), None, telemetry(), ())


class FakeRankingService(EvidenceRankingService):
    def rank(self, request):
        item = RankedEvidence(request.evidence_set.candidates[0], 1, 1.0, {"bm25": 1.0}, False)
        diagnostics = RankingDiagnostics(False, False, None, None, None, {"bm25": 1})
        return CapabilityResult("evidence.rank", True, RankedEvidenceSet("rs1", (item,), diagnostics), None, telemetry(), ())


class FakeContextService(ContextPackService):
    def build(self, request):
        block = ContextBlock("b1", "c1", "src/demo.py", 1, 1, "print('x')", 3, 1.0, "src/demo.py:1")
        pack = ContextPack("ctx1", "answer", "print('x')", (block,), 3, (), {"ok": True})
        return CapabilityResult("context.build", True, pack, None, telemetry(), ())


def registry(index_service=None, retrieval_service=None) -> ServiceRegistry:
    reg = ServiceRegistry()
    reg.register("index.validate", index_service or FakeIndexService())
    reg.register("evidence.retrieve", retrieval_service or FakeRetrievalService())
    reg.register("evidence.rank", FakeRankingService())
    reg.register("context.build", FakeContextService())
    return reg


def app_deps(tmp_path: Path):
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / ".homllm" / "runs")
    manager.create_run("run-1", {})
    writer = EventWriter(tmp_path / ".homllm" / "runs" / "run-1" / "events.jsonl")
    return manager, writer


def test_app_executes_services_and_returns_context(tmp_path: Path) -> None:
    manager, writer = app_deps(tmp_path)

    result = build_readonly_context(
        task_id="task-1",
        run_id="run-1",
        workspace_root=str(tmp_path),
        query="explain demo",
        service_registry=registry(),
        artifact_manager=manager,
        event_writer=writer,
        policy=read_only_milestone1_policy(),
    )

    assert result.ok is True
    assert result.output is not None
    assert result.output.text == "print('x')"
    events = (tmp_path / ".homllm" / "runs" / "run-1" / "events.jsonl").read_text(encoding="utf-8")
    assert "run_started" in events
    assert "index_validated" in events
    assert "retrieval_completed" in events
    assert "ranking_completed" in events
    assert "context_completed" in events
    assert "run_completed" in events


def test_app_stops_on_index_failure(tmp_path: Path) -> None:
    manager, writer = app_deps(tmp_path)

    result = build_readonly_context(
        task_id="task-1",
        run_id="run-1",
        workspace_root=str(tmp_path),
        query="explain demo",
        service_registry=registry(index_service=FailingIndexService()),
        artifact_manager=manager,
        event_writer=writer,
        policy=read_only_milestone1_policy(),
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "index_missing"


def test_app_stops_on_empty_evidence(tmp_path: Path) -> None:
    manager, writer = app_deps(tmp_path)

    result = build_readonly_context(
        task_id="task-1",
        run_id="run-1",
        workspace_root=str(tmp_path),
        query="explain demo",
        service_registry=registry(retrieval_service=EmptyRetrievalService()),
        artifact_manager=manager,
        event_writer=writer,
        policy=read_only_milestone1_policy(),
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "empty_evidence_set"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_readonly_context_app_contract.py -q
```

Expected:
- Fails because app, service shells, or context/ranking contracts do not exist.

- [ ] **Step 3: Implement evidence, ranking, and context contracts**

Add to `src/homllm_v4/contracts/evidence.py` below direct read contracts:

```python
@dataclass(frozen=True)
class EvidenceCandidate:
    candidate_id: str
    file_path: str
    symbol_id: str | None
    span_start: int | None
    span_end: int | None
    content_hash: str
    source_channels: tuple[str, ...]
    bm25_score: float | None
    vector_score: float | None
    graph_score: float | None
    retrieval_score: float
    metadata: dict[str, object]


@dataclass(frozen=True)
class RetrievalDiagnostics:
    bm25_count: int
    vector_count: int
    graph_added_count: int
    precision_added_count: int
    coverage_added_count: int
    retrieval_disagreement: float | None
    degraded: bool
    degradation_reason: str | None


@dataclass(frozen=True)
class EvidenceSet:
    evidence_set_id: str
    query: str
    candidates: tuple[EvidenceCandidate, ...]
    diagnostics: RetrievalDiagnostics


@dataclass(frozen=True)
class EvidenceRetrievalRequest:
    task_id: str
    query: str
    task_class: str
    index_id: str
    policy: dict[str, object]
    target_files: tuple[str, ...] = ()
    target_symbols: tuple[str, ...] = ()
```

Create `src/homllm_v4/contracts/ranking.py`:

```python
from dataclasses import dataclass

from homllm_v4.contracts.evidence import EvidenceCandidate, EvidenceSet


@dataclass(frozen=True)
class RankedEvidence:
    candidate: EvidenceCandidate
    rank: int
    final_score: float
    score_components: dict[str, float]
    reranked: bool


@dataclass(frozen=True)
class RankingDiagnostics:
    reranker_used: bool
    reranker_available: bool
    reranker_degraded_reason: str | None
    concentration_ratio: float | None
    score_separation: float | None
    top_source_channels: dict[str, int]


@dataclass(frozen=True)
class RankedEvidenceSet:
    ranked_set_id: str
    items: tuple[RankedEvidence, ...]
    diagnostics: RankingDiagnostics


@dataclass(frozen=True)
class EvidenceRankingRequest:
    task_id: str
    evidence_set: EvidenceSet
    policy: dict[str, object]
```

Create `src/homllm_v4/contracts/context.py`:

```python
from dataclasses import dataclass

from homllm_v4.contracts.ranking import RankedEvidenceSet


@dataclass(frozen=True)
class ContextBlock:
    block_id: str
    candidate_id: str
    file_path: str
    span_start: int | None
    span_end: int | None
    text: str
    token_count: int
    score: float
    citation: str


@dataclass(frozen=True)
class ContextPack:
    context_pack_id: str
    purpose: str
    text: str
    blocks: tuple[ContextBlock, ...]
    used_tokens: int
    dropped_candidates: tuple[str, ...]
    diagnostics: dict[str, object]


@dataclass(frozen=True)
class ContextPackRequest:
    task_id: str
    ranked_evidence_set: RankedEvidenceSet
    policy: dict[str, object]
```

- [ ] **Step 4: Implement service shell base methods**

Create `src/homllm_v4/services/retrieval_service.py`:

```python
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.evidence import EvidenceRetrievalRequest, EvidenceSet


class EvidenceRetrievalService:
    def retrieve(self, request: EvidenceRetrievalRequest) -> CapabilityResult[EvidenceSet]:
        raise NotImplementedError("adapter-backed retrieval is added after app contract tests")
```

Create `src/homllm_v4/services/ranking_service.py`:

```python
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.ranking import EvidenceRankingRequest, RankedEvidenceSet


class EvidenceRankingService:
    def rank(self, request: EvidenceRankingRequest) -> CapabilityResult[RankedEvidenceSet]:
        raise NotImplementedError("adapter-backed ranking is added after app contract tests")
```

Create `src/homllm_v4/services/context_service.py`:

```python
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.context import ContextPack, ContextPackRequest


class ContextPackService:
    def build(self, request: ContextPackRequest) -> CapabilityResult[ContextPack]:
        raise NotImplementedError("adapter-backed context build is added after app contract tests")
```

- [ ] **Step 5: Implement readonly context app**

Create `src/homllm_v4/app/readonly_context_app.py`:

```python
from uuid import uuid4

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.context import ContextPack, ContextPackRequest
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.evidence import EvidenceRetrievalRequest
from homllm_v4.contracts.index import IndexRequest
from homllm_v4.contracts.policy import CapabilityPolicy
from homllm_v4.contracts.ranking import EvidenceRankingRequest
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.ledger.events import (
    CONTEXT_COMPLETED,
    INDEX_VALIDATED,
    POLICY_CREATED,
    RANKING_COMPLETED,
    RETRIEVAL_COMPLETED,
    RUN_COMPLETED,
    RUN_STARTED,
    SERVICE_FAILED,
    RunEvent,
)
from homllm_v4.ledger.writer import EventWriter
from homllm_v4.registry.service_registry import ServiceRegistry
from homllm_v4.services.context_service import ContextPackService
from homllm_v4.services.index_service import IndexService
from homllm_v4.services.ranking_service import EvidenceRankingService
from homllm_v4.services.retrieval_service import EvidenceRetrievalService


def build_readonly_context(
    *,
    task_id: str,
    run_id: str,
    workspace_root: str,
    query: str,
    service_registry: ServiceRegistry,
    artifact_manager: ArtifactManager,
    event_writer: EventWriter,
    policy: CapabilityPolicy,
) -> CapabilityResult[ContextPack]:
    _append(event_writer, run_id, task_id, "created", RUN_STARTED, {"query": query})
    _append(event_writer, run_id, task_id, "policy", POLICY_CREATED, {"permission_profile": policy.permission_profile})

    index_service = service_registry.get("index.validate", IndexService)
    index_result = index_service.validate(
        IndexRequest(
            workspace_root=workspace_root,
            include_patterns=("**/*.py",),
            exclude_patterns=(".git/**",),
            language_profile="python",
            mode="validate",
            artifact_paths={},
        )
    )
    if not index_result.ok:
        _append(event_writer, run_id, task_id, "index", SERVICE_FAILED, {"service": "index.validate"})
        return _failed_context(index_result)
    _append(event_writer, run_id, task_id, "index", INDEX_VALIDATED, {"ok": True})

    retrieval_service = service_registry.get("evidence.retrieve", EvidenceRetrievalService)
    retrieval_result = retrieval_service.retrieve(
        EvidenceRetrievalRequest(
            task_id=task_id,
            query=query,
            task_class="answer",
            index_id=index_result.output.manifest.index_id,
            policy={},
        )
    )
    if not retrieval_result.ok:
        _append(event_writer, run_id, task_id, "retrieval", SERVICE_FAILED, {"service": "evidence.retrieve"})
        return _failed_context(retrieval_result)
    if not retrieval_result.output.candidates:
        _append(event_writer, run_id, task_id, "retrieval", SERVICE_FAILED, {"service": "evidence.retrieve", "reason": "empty"})
        return CapabilityResult(
            capability_name="context.build_readonly",
            ok=False,
            output=None,
            error=CapabilityError("empty_evidence_set", "retrieval returned no candidates", True, False, {}),
            telemetry=_telemetry(),
            artifacts=(),
        )
    _append(event_writer, run_id, task_id, "retrieval", RETRIEVAL_COMPLETED, {"candidate_count": len(retrieval_result.output.candidates)})

    ranking_service = service_registry.get("evidence.rank", EvidenceRankingService)
    ranking_result = ranking_service.rank(EvidenceRankingRequest(task_id=task_id, evidence_set=retrieval_result.output, policy={}))
    if not ranking_result.ok:
        _append(event_writer, run_id, task_id, "ranking", SERVICE_FAILED, {"service": "evidence.rank"})
        return _failed_context(ranking_result)
    _append(event_writer, run_id, task_id, "ranking", RANKING_COMPLETED, {"item_count": len(ranking_result.output.items)})

    context_service = service_registry.get("context.build", ContextPackService)
    context_result = context_service.build(ContextPackRequest(task_id=task_id, ranked_evidence_set=ranking_result.output, policy={}))
    if not context_result.ok:
        _append(event_writer, run_id, task_id, "context", SERVICE_FAILED, {"service": "context.build"})
        return context_result
    _append(event_writer, run_id, task_id, "context", CONTEXT_COMPLETED, {"block_count": len(context_result.output.blocks)})
    _append(event_writer, run_id, task_id, "stopped", RUN_COMPLETED, {"ok": True})
    return context_result


def _append(writer: EventWriter, run_id: str, task_id: str, phase: str, event_type: str, summary: dict[str, object]) -> None:
    writer.append(
        RunEvent(
            event_id=str(uuid4()),
            run_id=run_id,
            task_id=task_id,
            phase=phase,
            event_type=event_type,
            timestamp="",
            summary=summary,
            artifact_refs=(),
        )
    )


def _failed_context(result: CapabilityResult[object]) -> CapabilityResult[ContextPack]:
    return CapabilityResult(
        capability_name="context.build_readonly",
        ok=False,
        output=None,
        error=result.error,
        telemetry=result.telemetry,
        artifacts=result.artifacts,
    )


def _telemetry() -> CapabilityTelemetry:
    return CapabilityTelemetry(
        started_at="",
        ended_at="",
        duration_ms=0,
        input_summary={},
        output_summary={},
        token_usage={},
        model_usage={},
        degraded=False,
        degradation_reason=None,
    )
```

Create `src/homllm_v4/app/__init__.py`.

- [ ] **Step 6: Run readonly app tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_readonly_context_app_contract.py -q
```

Expected:
- All readonly context app tests pass.

- [ ] **Step 7: Run all v4 unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4 -q
```

Expected:
- All v4 unit tests pass.

- [ ] **Step 8: Checkpoint**

Do not commit unless explicitly authorized.

## Task 9: Final Milestone 1 Verification

**Files:**
- Read/check all files created in Tasks 1-8.
- No new implementation files should be added in this task.

- [ ] **Step 1: Run all v4 unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4 -q
```

Expected:
- All tests pass.

- [ ] **Step 2: Run boundary test explicitly**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_v3_adapter_boundaries.py -q
```

Expected:
- Boundary tests pass.

- [ ] **Step 3: Run a focused broader unit check if runtime permits**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit -q
```

Expected:
- Existing unit tests pass.
- If this is too slow or fails due unrelated existing environment issues, record exact failure and continue with v4 test evidence.

- [ ] **Step 4: Inspect v4 file sizes**

Run:

```powershell
Get-ChildItem -Path 'src/homllm_v4','tests/unit/v4' -Recurse -File | Select-Object FullName,Length | Format-Table -AutoSize
```

Expected:
- No new file is unexpectedly large.
- No file mixes multiple unrelated responsibilities.

- [ ] **Step 5: Inspect git status for scoped changes**

Run:

```powershell
git status --short src/homllm_v4 tests/unit/v4
```

Expected:
- Changes are limited to `src/homllm_v4/` and `tests/unit/v4/` for implementation.

- [ ] **Step 6: Completion summary**

Report:
- tests run
- files created
- architectural boundaries preserved
- any skipped verification
- known limitations

Do not claim real v3 retrieval/ranking/context integration is complete unless a real-v3 smoke test was implemented and passed.

## Execution Notes

- The first implementation pass intentionally uses fake services for the readonly app contract.
- Real v3 adapter translation can follow after this shell is stable and boundary tests exist.
- This plan intentionally does not add adapter-backed retrieval/ranking/context behavior beyond shells.
- If the user wants real-v3 adapter smoke tests in Milestone 1, create a follow-up plan section after checking available fixture artifacts.

