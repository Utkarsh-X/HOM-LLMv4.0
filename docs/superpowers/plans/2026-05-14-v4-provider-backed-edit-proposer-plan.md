# V4 Provider-Backed Edit Proposer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first provider-backed edit proposal seam so a model/provider can propose bounded file content from runtime-fixed evidence, without granting provider code authority over scope, patching, or execution.

**Architecture:** The new proposer lives in pure v4 planning code and depends only on v4 contracts plus an injected provider protocol. It builds a constrained prompt, parses a JSON provider response into `EditProposalResult`, validates evidence and file scope, and delegates final runtime checks to `BoundedEditProposer`.

**Tech Stack:** Python dataclasses/protocols, pytest, existing v4 `CapabilityResult`, existing `BoundedEditProposer`.

---

## File Structure

- Create `src/homllm_v4/planning/provider_edit_proposer.py`
  - Defines provider request/response contracts, provider protocol, prompt builder, JSON parsing, response validation, and `ProviderBackedEditProposer`.
- Modify `src/homllm_v4/planning/__init__.py`
  - Exports the new proposer contracts.
- Create `tests/unit/v4/test_provider_edit_proposer.py`
  - Tests provider prompt construction, valid parsing, invalid JSON, missing fields, file-scope denial, evidence-scope denial, and token/model telemetry propagation.
- Modify `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - Records the M6 provider-backed proposal seam.
- Modify `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Updates the checklist and remaining gaps.

## Task 1: Provider Proposer Tests

**Files:**
- Create: `tests/unit/v4/test_provider_edit_proposer.py`

- [ ] **Step 1: Write failing tests for valid provider JSON**

Add tests with a fake provider:

```python
from dataclasses import dataclass

from homllm_v4.contracts.edit_proposal import EditProposalRequest
from homllm_v4.planning.provider_edit_proposer import (
    ProviderBackedEditProposer,
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
)


@dataclass
class FakeProvider:
    response_text: str
    last_request: ProviderEditProposalRequest | None = None

    def propose_edit(self, request: ProviderEditProposalRequest) -> ProviderEditProposalResponse:
        self.last_request = request
        return ProviderEditProposalResponse(
            text=self.response_text,
            tokens_in=11,
            tokens_out=7,
            model="fake-model",
            metadata={"provider": "fake"},
        )


def proposal_request() -> EditProposalRequest:
    return EditProposalRequest(
        task_id="task-1",
        target_file="calculator.py",
        intent="fix add",
        expected_behavior="add returns a sum",
        current_content="def add(a, b):\n    return a - b\n",
        evidence_ids=("cand-1",),
        allowed_file_paths=("calculator.py",),
        verification_summary="pytest . -q",
    )


def test_provider_backed_edit_proposer_accepts_valid_json_response() -> None:
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use addition.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    proposer = ProviderBackedEditProposer(provider=provider)

    result = proposer.propose(proposal_request())

    assert result.ok is True
    assert result.output is not None
    assert result.output.target_file == "calculator.py"
    assert "return a + b" in result.output.new_content
    assert result.telemetry.token_usage == {"input": 11, "output": 7}
    assert result.telemetry.model_usage == {"model": "fake-model", "provider": "fake"}
    assert provider.last_request is not None
    assert "calculator.py" in provider.last_request.prompt
    assert "cand-1" in provider.last_request.prompt
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py::test_provider_backed_edit_proposer_accepts_valid_json_response -q
```

Expected: FAIL because `homllm_v4.planning.provider_edit_proposer` does not exist.

- [ ] **Step 3: Add failing tests for provider response failures**

Add tests:

```python
def test_provider_backed_edit_proposer_rejects_invalid_json() -> None:
    proposer = ProviderBackedEditProposer(provider=FakeProvider("not json"))

    result = proposer.propose(proposal_request())

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "provider_response_invalid"


def test_provider_backed_edit_proposer_rejects_missing_required_key() -> None:
    proposer = ProviderBackedEditProposer(
        provider=FakeProvider('{"target_file":"calculator.py"}')
    )

    result = proposer.propose(proposal_request())

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "provider_response_invalid"
```

- [ ] **Step 4: Add failing tests for runtime scope enforcement**

Add tests:

```python
def test_provider_backed_edit_proposer_rejects_unapproved_target_file() -> None:
    proposer = ProviderBackedEditProposer(
        provider=FakeProvider(
            '{"target_file":"other.py",'
            '"new_content":"x",'
            '"rationale":"bad",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )

    result = proposer.propose(proposal_request())

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "proposal_file_denied"


def test_provider_backed_edit_proposer_rejects_unknown_evidence_id() -> None:
    proposer = ProviderBackedEditProposer(
        provider=FakeProvider(
            '{"target_file":"calculator.py",'
            '"new_content":"x",'
            '"rationale":"bad",'
            '"evidence_ids":["unknown"],'
            '"risk_flags":[]}'
        )
    )

    result = proposer.propose(proposal_request())

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "proposal_evidence_scope_denied"
```

## Task 2: Minimal Provider Proposer Implementation

**Files:**
- Create: `src/homllm_v4/planning/provider_edit_proposer.py`
- Modify: `src/homllm_v4/planning/__init__.py`

- [ ] **Step 1: Implement pure v4 provider protocol and proposer**

Create `src/homllm_v4/planning/provider_edit_proposer.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from time import perf_counter
from typing import Protocol

from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.edit_proposal import EditProposalRequest, EditProposalResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.planning.bounded_edit_proposer import BoundedEditProposer


@dataclass(frozen=True)
class ProviderEditProposalRequest:
    task_id: str
    prompt: str
    response_format: str = "json"


@dataclass(frozen=True)
class ProviderEditProposalResponse:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = "unknown"
    metadata: dict[str, object] = field(default_factory=dict)


class EditProposalProvider(Protocol):
    def propose_edit(
        self,
        request: ProviderEditProposalRequest,
    ) -> ProviderEditProposalResponse:
        ...


class ProviderBackedEditProposer:
    def __init__(self, *, provider: EditProposalProvider) -> None:
        self.provider = provider

    def propose(self, request: EditProposalRequest) -> CapabilityResult[EditProposalResult]:
        started = perf_counter()
        provider_response: ProviderEditProposalResponse | None = None
        try:
            provider_response = self.provider.propose_edit(
                ProviderEditProposalRequest(
                    task_id=request.task_id,
                    prompt=build_edit_proposal_prompt(request),
                )
            )
            proposal = parse_provider_edit_response(provider_response.text)
        except Exception as exc:
            return _failed(
                request=request,
                started=started,
                provider_response=provider_response,
                code="provider_response_invalid",
                message=str(exc),
            )

        unknown_evidence = sorted(set(proposal.evidence_ids) - set(request.evidence_ids))
        if unknown_evidence:
            return _failed(
                request=request,
                started=started,
                provider_response=provider_response,
                code="proposal_evidence_scope_denied",
                message="proposal references evidence ids outside the request",
                details={"unknown_evidence_ids": unknown_evidence},
            )

        bounded = BoundedEditProposer(proposer=lambda _: proposal).propose(request)
        return _with_provider_usage(
            bounded,
            started=started,
            provider_response=provider_response,
            request=request,
        )
```

Then complete the helper functions in the same file:

```python
def build_edit_proposal_prompt(request: EditProposalRequest) -> str:
    return "\n".join(
        (
            "You are proposing a bounded single-file edit.",
            "Return only JSON with keys: target_file, new_content, rationale, evidence_ids, risk_flags.",
            f"Task ID: {request.task_id}",
            f"Target file: {request.target_file}",
            f"Allowed files: {', '.join(request.allowed_file_paths)}",
            f"Intent: {request.intent}",
            f"Expected behavior: {request.expected_behavior}",
            f"Evidence IDs: {', '.join(request.evidence_ids)}",
            f"Verification: {request.verification_summary}",
            "Current content:",
            request.current_content,
        )
    )


def parse_provider_edit_response(text: str) -> EditProposalResult:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("provider response must be a JSON object")

    required = ("target_file", "new_content", "rationale", "evidence_ids", "risk_flags")
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"provider response missing keys: {', '.join(missing)}")

    if not isinstance(data["evidence_ids"], list):
        raise ValueError("provider response evidence_ids must be a list")
    if not isinstance(data["risk_flags"], list):
        raise ValueError("provider response risk_flags must be a list")

    return EditProposalResult(
        target_file=_string_field(data, "target_file"),
        new_content=_string_field(data, "new_content"),
        rationale=_string_field(data, "rationale"),
        evidence_ids=tuple(str(item) for item in data["evidence_ids"]),
        risk_flags=tuple(str(item) for item in data["risk_flags"]),
    )
```

- [ ] **Step 2: Export the new proposer**

Modify `src/homllm_v4/planning/__init__.py` to export:

```python
from homllm_v4.planning.provider_edit_proposer import (
    EditProposalProvider,
    ProviderBackedEditProposer,
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
)
```

- [ ] **Step 3: Run targeted tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_provider_edit_proposer.py -q
```

Expected: all provider proposer tests pass.

## Task 3: Documentation and Verification

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Update architecture audit**

Add that M6 now has a provider-backed proposal seam with fake-provider tests, still no real LLM synthesis or production UX.

- [ ] **Step 2: Update active goal audit**

Update checklist:

```text
Provider-backed edit proposal seam exists | ProviderBackedEditProposer with injected provider, JSON parsing, bounded validation, tests | Satisfied for fake-provider seam only
```

Keep the goal incomplete because real LLM patch synthesis, broad write benchmark, rollback, sandbox backend, approval UX, and product session model remain incomplete.

- [ ] **Step 3: Run full verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected:

- v4 tests pass.
- unit tests pass.
- compileall exits successfully.
- boundary scan returns no matches.

Run opt-in smoke checks:

```powershell
$env:HOMLLM_V4_RUN_REAL_V3_SMOKE='1'; .\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_read_only_loop_smoke tests\unit\v4\test_v3_read_only_factory.py::test_real_v3_retrieval_backed_patch_planner_smoke -q -s
.\.venv\Scripts\python.exe runtime\v4_cli.py eval-fixture-patch --fixture-root fixtures\v4\python_patch_repo --workspace-root temp\v4_fixture_patch_work_provider --artifact-root temp\v4_fixture_patch_runs_provider --run-id provider-proposer-check
```

Expected:

- real v3 smoke passes.
- fixture CLI reports `failed_cases: 0`.

## Self-Review

- Spec coverage: This plan covers only the provider-backed proposal seam. It intentionally does not implement real provider adapters, autonomous target selection, rollback, approval UX, OS sandboxing, or product session flow.
- Placeholder scan: No TBD/TODO placeholders are present.
- Type consistency: `ProviderEditProposalRequest`, `ProviderEditProposalResponse`, `EditProposalProvider`, and `ProviderBackedEditProposer` are consistently named across tests and implementation.
