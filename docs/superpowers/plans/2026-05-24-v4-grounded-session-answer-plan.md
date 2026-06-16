# v4 Grounded Session Answer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `agent-session` answer repository questions with a provider-synthesized grounded answer from retrieved context, while preserving deterministic read-only retrieval and existing edit/verify behavior.

**Architecture:** Add a small session-edge answer synthesizer that consumes `ReadOnlyLoopResult.context_pack` and calls the existing v4 provider protocol DTOs. The deterministic read-only loop continues to own retrieval, ranking, context building, and sufficiency; `agent-session` owns optional provider answer synthesis, artifacts, telemetry, and fallback behavior. This keeps live LLM behavior at the user-facing edge and preserves rollback-aware edit execution.

**Tech Stack:** Python dataclasses, existing provider DTOs from `provider_edit_proposer`, `ArtifactManager`, argparse, pytest.

---

## File Structure

- Create `src/homllm_v4/runtime/grounded_answer.py`
  - Owns `GroundedAnswerRequest`, `GroundedAnswerResult`, and `GroundedAnswerSynthesizer`.
  - Builds a bounded prompt from the query and context blocks.
  - Calls an injected provider using `ProviderEditProposalRequest`/`ProviderEditProposalResponse`.
  - Writes prompt and response artifacts when an `ArtifactManager` is supplied.
  - Returns structured error codes for missing context, prompt budget exceeded, provider invocation failure, and empty provider response.
- Modify `src/homllm_v4/runtime/agent_session.py`
  - Add answer synthesis fields to `AgentSessionRequest`/`AgentSessionResult`.
  - After read-only ask, optionally synthesize a grounded answer.
  - If synthesis fails, preserve the deterministic read-only response and expose the answer error code.
  - Use the same live provider builder as `agent-task`.
- Modify `src/homllm_v4/cli.py`
  - Add `--answer-provider-mode` with values `live` and `summary`, defaulting to `summary` for safe-by-default ask-only runs.
  - Reuse existing live provider args and API-key env handling.
  - Include answer telemetry/error fields in JSON output.
- Modify `src/homllm_v4/api.py`
  - Re-export the grounded answer types.
- Create `tests/unit/v4/test_grounded_answer.py`
  - Unit tests for prompt content, artifacts, prompt budget failure, missing context, and provider failure.
- Modify `tests/unit/v4/test_agent_session.py`
  - Tests for provider answer synthesis success and fallback on answer failure.
- Modify `tests/unit/v4/test_cli_api.py`
  - Test CLI propagation and JSON output for live grounded answer synthesis.
- Update `docs/v4_architecture/09-active-goal-completion-audit.md`
  - Record that session ask can now synthesize grounded provider answers from retrieved context, with caveats.

## Task 1: Grounded Answer Synthesizer

**Files:**
- Create: `tests/unit/v4/test_grounded_answer.py`
- Create: `src/homllm_v4/runtime/grounded_answer.py`

- [x] **Step 1: Write failing synthesizer success test**

Add a test that builds a `ContextPack` with two blocks, injects a fake provider, runs `GroundedAnswerSynthesizer.synthesize`, and asserts:

- provider prompt contains the query
- provider prompt contains both citations and snippets
- returned answer text is provider text
- token usage and model are reflected in telemetry
- prompt and response artifacts are written

- [x] **Step 2: Run success test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_grounded_answer.py::test_grounded_answer_synthesizer_uses_context_and_writes_artifacts -q
```

Expected: fail because `homllm_v4.runtime.grounded_answer` does not exist.

- [x] **Step 3: Implement minimal synthesizer success path**

Create `GroundedAnswerRequest`, `GroundedAnswerResult`, and `GroundedAnswerSynthesizer`. The provider call should use:

```python
ProviderEditProposalRequest(task_id=request.task_id, prompt=prompt, response_format="text")
```

The prompt must instruct the provider to answer only from supplied repository context, cite files using the provided citations, and say when context is insufficient.

- [x] **Step 4: Run success test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_grounded_answer.py::test_grounded_answer_synthesizer_uses_context_and_writes_artifacts -q
```

Expected: pass.

- [x] **Step 5: Add failure/budget tests**

Add tests for:

- no context pack returns `ok=False` and `error_code="answer_context_missing"` without provider call
- prompt above `max_prompt_chars` returns `ok=False` and `error_code="answer_prompt_budget_exceeded"` without provider call
- provider exception returns `ok=False` and `error_code="answer_provider_invocation_failed"`
- blank provider text returns `ok=False` and `error_code="answer_provider_empty_response"`

- [x] **Step 6: Run failure/budget tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_grounded_answer.py -q
```

Expected: fail until the failure paths are implemented. In execution, the failure tests were written before production code, and the full file was run after the minimal implementation.

- [x] **Step 7: Implement failure/budget paths**

Add structured result handling. Do not raise for expected answer synthesis failures.

- [x] **Step 8: Run synthesizer tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_grounded_answer.py -q
```

Expected: pass.

## Task 2: Session API Integration

**Files:**
- Modify: `tests/unit/v4/test_agent_session.py`
- Modify: `src/homllm_v4/runtime/agent_session.py`
- Modify: `src/homllm_v4/api.py`

- [x] **Step 1: Write failing session synthesis test**

Add a test where the injected read-only runner returns a `ReadOnlyLoopResult` with context. Inject an `answer_synthesizer` fake that returns `"Grounded provider answer."`. Assert `run_agent_session` returns that answer, preserves ask run id, and exposes answer metrics.

- [x] **Step 2: Run session synthesis test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_session.py::test_run_agent_session_synthesizes_grounded_answer_from_context -q
```

Expected: fail because session request/result do not support answer synthesis.

- [x] **Step 3: Implement session answer integration**

Add request fields:

```python
answer_provider_mode: str = "summary"
answer_synthesizer: Any = None
answer_provider_builder: Any = build_v3_provider_edit_adapter_from_params
```

Add result fields for answer status:

```python
answer_provider_mode: str
answer_error_code: str | None
answer_metrics: dict[str, object]
```

If mode is `summary`, skip synthesis. If mode is `live`, require `live_api_key`, build the provider, create an `ArtifactManager` for `<ask_run_id>`, and synthesize from the read-only result.

- [x] **Step 4: Run session synthesis test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_session.py::test_run_agent_session_synthesizes_grounded_answer_from_context -q
```

Expected: pass.

- [x] **Step 5: Add fallback test**

Add a test proving answer synthesis failure keeps the original read-only `response_text`, sets `answer_error_code`, and does not block edit execution.

- [x] **Step 6: Run session tests to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_agent_session.py -q
```

Expected: pass.

## Task 3: CLI Integration

**Files:**
- Modify: `tests/unit/v4/test_cli_api.py`
- Modify: `src/homllm_v4/cli.py`

- [x] **Step 1: Write failing CLI test**

Extend `test_cli_agent_session_prints_combined_json` or add a focused test proving:

- `--answer-provider-mode live` reaches `AgentSessionRequest`
- `live_api_key` is read from the configured env var
- JSON output includes `answer_provider_mode`, `answer_error_code`, and `answer_metrics`

- [x] **Step 2: Run CLI test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_cli_api.py::test_cli_agent_session_prints_combined_json -q
```

Expected: fail until CLI output/request fields are wired.

- [x] **Step 3: Implement CLI wiring**

Add parser argument:

```python
agent_session.add_argument("--answer-provider-mode", choices=("live", "summary"), default="summary")
```

Include the new request fields and JSON fields. Preserve existing ask/edit behavior.

- [x] **Step 4: Run CLI test to verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_cli_api.py::test_cli_agent_session_prints_combined_json -q
```

Expected: pass.

## Task 4: Verification, Live Smoke, And Audit

**Files:**
- Modify: `docs/v4_architecture/09-active-goal-completion-audit.md`
- Modify: this plan file

- [x] **Step 1: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\v4\test_grounded_answer.py tests\unit\v4\test_agent_session.py tests\unit\v4\test_cli_api.py tests\unit\v4\test_agent_task.py tests\unit\v4\test_provider_fixture_cli.py -q
```

Expected: pass.

- [x] **Step 2: Run compile verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q src\homllm_v4 tests\unit\v4 runtime\v4_cli.py
```

Expected: pass.

- [x] **Step 3: Run opt-in live session answer smoke**

Use a copied fixture workspace and `agent-session --prepare-index --index-skip-vectors --answer-provider-mode live` with Gemini. The expected outcome is exit code `0`, a natural answer mentioning the relevant fixture file/function, answer token metrics, and persisted answer prompt/response artifacts.

- [x] **Step 4: Update audit and plan checkboxes**

Record fresh unit, compile, and live smoke evidence. Keep the overall active goal open unless the full objective is proven.
