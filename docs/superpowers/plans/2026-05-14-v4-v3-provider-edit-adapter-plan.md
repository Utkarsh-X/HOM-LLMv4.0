# V4 V3 Provider Edit Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the v4 provider-backed edit proposal seam to the existing v3 provider connector contract through an adapter that lives only inside `src/homllm_v4/adapters/`.

**Architecture:** v4 planning remains pure and imports no v3 code. The new adapter translates `ProviderEditProposalRequest` into v3 `ProviderRequest`, invokes a v3 `ProviderConnector`, and translates v3 `ProviderResponse` back into `ProviderEditProposalResponse`.

**Tech Stack:** Python dataclasses/protocols, v3 generation interfaces, pytest, existing v4 provider edit proposer.

---

## File Structure

- Create `src/homllm_v4/adapters/v3_provider_edit_proposer.py`
  - Owns all translation between v4 provider edit proposal contracts and v3 generation provider connector contracts.
- Modify `src/homllm_v4/adapters/__init__.py`
  - Export `V3ProviderEditProposalAdapter`.
- Create `tests/unit/v4/test_v3_provider_edit_proposer_adapter.py`
  - Tests adapter request/response translation with a fake v3 connector only.
- Modify `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
  - Records the v3 provider adapter seam.
- Modify `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Updates remaining gaps from "no provider adapter" to "no live LLM smoke/evaluation".

## Task 1: Adapter Translation Tests

**Files:**
- Create: `tests/unit/v4/test_v3_provider_edit_proposer_adapter.py`

- [ ] **Step 1: Write failing test for v3 provider request/response translation**

```python
from collections.abc import Callable

from homllm.generation.interfaces import (
    ModelConfig,
    ProviderCapabilities,
    ProviderRequest,
    ProviderResponse,
)
from homllm_v4.adapters.v3_provider_edit_proposer import V3ProviderEditProposalAdapter
from homllm_v4.planning.provider_edit_proposer import ProviderEditProposalRequest


class FakeV3ProviderConnector:
    def __init__(self, response: ProviderResponse) -> None:
        self.response = response
        self.last_request: ProviderRequest | None = None

    def invoke_sync(self, request: ProviderRequest) -> ProviderResponse:
        self.last_request = request
        return self.response

    def invoke_stream(
        self,
        request: ProviderRequest,
        on_chunk: Callable[[str], None],
    ) -> ProviderResponse:
        raise AssertionError("streaming should not be used for edit proposals")

    def healthcheck(self) -> bool:
        return True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            streaming=False,
            max_tokens=4096,
            rate_limits={},
            supports_seed=False,
            supports_json_mode=False,
        )


def test_v3_provider_edit_adapter_translates_request_and_response() -> None:
    connector = FakeV3ProviderConnector(
        ProviderResponse(
            text='{"target_file":"calculator.py"}',
            tokens_in=12,
            tokens_out=8,
            finish_reason="stop",
            model="fake-v3-model",
            metadata={"provider": "fake-v3"},
        )
    )
    model_config = ModelConfig(temperature=0.0, max_output_tokens=2048)
    adapter = V3ProviderEditProposalAdapter(
        provider=connector,
        model="configured-model",
        model_config=model_config,
    )

    result = adapter.propose_edit(
        ProviderEditProposalRequest(
            task_id="task-1",
            prompt="Return JSON.",
        )
    )

    assert connector.last_request is not None
    assert connector.last_request.prompt == "Return JSON."
    assert connector.last_request.model == "configured-model"
    assert connector.last_request.config == model_config
    assert connector.last_request.stream is False
    assert result.text == '{"target_file":"calculator.py"}'
    assert result.tokens_in == 12
    assert result.tokens_out == 8
    assert result.model == "fake-v3-model"
    assert result.metadata == {"provider": "fake-v3", "finish_reason": "stop"}
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_provider_edit_proposer_adapter.py::test_v3_provider_edit_adapter_translates_request_and_response -q
```

Expected: FAIL because `homllm_v4.adapters.v3_provider_edit_proposer` does not exist.

- [ ] **Step 3: Write failing integration test with provider-backed proposer**

Add:

```python
from homllm_v4.contracts.edit_proposal import EditProposalRequest
from homllm_v4.planning.provider_edit_proposer import ProviderBackedEditProposer


def test_v3_provider_edit_adapter_can_drive_provider_backed_proposer() -> None:
    connector = FakeV3ProviderConnector(
        ProviderResponse(
            text=(
                '{"target_file":"calculator.py",'
                '"new_content":"def add(a, b):\\n    return a + b\\n",'
                '"rationale":"Use addition.",'
                '"evidence_ids":["cand-1"],'
                '"risk_flags":[]}'
            ),
            tokens_in=12,
            tokens_out=8,
            finish_reason="stop",
            model="fake-v3-model",
            metadata={"provider": "fake-v3"},
        )
    )
    adapter = V3ProviderEditProposalAdapter(
        provider=connector,
        model="configured-model",
        model_config=ModelConfig(temperature=0.0, max_output_tokens=2048),
    )
    proposer = ProviderBackedEditProposer(provider=adapter)

    result = proposer.propose(
        EditProposalRequest(
            task_id="task-1",
            target_file="calculator.py",
            intent="fix add",
            expected_behavior="add returns a sum",
            current_content="def add(a, b):\n    return a - b\n",
            evidence_ids=("cand-1",),
            allowed_file_paths=("calculator.py",),
            verification_summary="pytest . -q",
        )
    )

    assert result.ok is True
    assert result.output is not None
    assert "return a + b" in result.output.new_content
    assert result.telemetry.model_usage["provider"] == "fake-v3"
```

## Task 2: Adapter Implementation

**Files:**
- Create: `src/homllm_v4/adapters/v3_provider_edit_proposer.py`
- Modify: `src/homllm_v4/adapters/__init__.py`

- [ ] **Step 1: Implement v3 provider connector adapter**

```python
from __future__ import annotations

from dataclasses import dataclass

from homllm.generation.interfaces import ModelConfig, ProviderConnector, ProviderRequest
from homllm_v4.planning.provider_edit_proposer import (
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
)


@dataclass(frozen=True)
class V3ProviderEditProposalAdapter:
    provider: ProviderConnector
    model: str
    model_config: ModelConfig

    def propose_edit(
        self,
        request: ProviderEditProposalRequest,
    ) -> ProviderEditProposalResponse:
        response = self.provider.invoke_sync(
            ProviderRequest(
                prompt=request.prompt,
                model=self.model,
                config=self.model_config,
                stream=False,
            )
        )
        return ProviderEditProposalResponse(
            text=response.text,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            model=response.model,
            metadata={**response.metadata, "finish_reason": response.finish_reason},
        )
```

- [ ] **Step 2: Export adapter**

Add to `src/homllm_v4/adapters/__init__.py`:

```python
from homllm_v4.adapters.v3_provider_edit_proposer import V3ProviderEditProposalAdapter

__all__ = (..., "V3ProviderEditProposalAdapter")
```

- [ ] **Step 3: Run targeted adapter tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_v3_provider_edit_proposer_adapter.py -q
```

Expected: all adapter tests pass.

## Task 3: Documentation and Verification

**Files:**
- Modify: `docs/v4_architecture/08-milestone-1-4-implementation-audit.md`
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`

- [ ] **Step 1: Update docs**

Record:

```text
V3ProviderEditProposalAdapter connects v4 provider proposal contracts to v3 ProviderConnector under adapters/ only.
```

Retain the limitation:

```text
No live provider smoke or real LLM patch synthesis is enabled by default.
```

- [ ] **Step 2: Run verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4 -q
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m compileall -q src\homllm src\homllm_v4 tests\unit runtime\v4_cli.py eval\run_regression_cluster_audit.py
Get-ChildItem -Path src\homllm_v4 -Recurse -Filter *.py | Where-Object { $_.FullName -notmatch '\\adapters\\' } | Select-String -Pattern 'from homllm\.|import homllm\.'
```

Expected:

- v4 tests pass.
- full unit suite passes.
- compileall passes.
- boundary scan returns no matches.

## Self-Review

- Spec coverage: This plan covers only v4-to-v3 provider connector translation. It does not call real providers or synthesize patches live.
- Placeholder scan: No TBD/TODO placeholders are present.
- Type consistency: v4 provider contract names match the prior M6 seam.
