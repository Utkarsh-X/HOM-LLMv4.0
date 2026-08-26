import pytest
from dataclasses import dataclass
from pathlib import Path

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.edit_proposal import EditProposalEvidenceContext, EditProposalRequest
from homllm_v4.planning.provider_edit_proposer import (
    ProviderBackedEditProposer,
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
    parse_provider_edit_response,
)


@dataclass
class FakeProvider:
    response_text: str
    metadata: dict[str, object] | None = None
    last_request: ProviderEditProposalRequest | None = None

    def propose_edit(self, request: ProviderEditProposalRequest) -> ProviderEditProposalResponse:
        self.last_request = request
        return ProviderEditProposalResponse(
            text=self.response_text,
            tokens_in=11,
            tokens_out=7,
            model="fake-model",
            metadata={"provider": "fake", **(self.metadata or {})},
        )


def proposal_request(proposal_mode: str = "unified_diff") -> EditProposalRequest:
    return EditProposalRequest(
        task_id="task-1",
        target_file="calculator.py",
        intent="fix add",
        expected_behavior="add returns a sum",
        current_content="def add(a, b):\n    return a - b\n",
        evidence_ids=("cand-1",),
        allowed_file_paths=("calculator.py",),
        verification_summary="pytest . -q",
        proposal_mode=proposal_mode,
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

    result = proposer.propose(proposal_request("full_content"))

    assert result.ok is True
    assert result.output is not None
    assert result.output.target_file == "calculator.py"
    assert "return a + b" in result.output.new_content
    assert result.telemetry.token_usage == {"input": 11, "output": 7}
    assert result.telemetry.model_usage == {"model": "fake-model", "provider": "fake"}
    assert provider.last_request is not None
    assert "calculator.py" in provider.last_request.prompt
    assert "cand-1" in provider.last_request.prompt
    assert (
        "new_content must be the complete replacement content for the entire target file"
        in provider.last_request.prompt
    )
    assert (
        "Do not return a snippet, diff, patch, or partial function body"
        in provider.last_request.prompt
    )
    assert (
        "new_content must be a valid JSON string with escaped newlines and quotes"
        in provider.last_request.prompt
    )
    assert "Do not use Python triple-quoted strings" in provider.last_request.prompt
    assert (
        "For no-op or validation-only tasks, return current content unchanged"
        in provider.last_request.prompt
    )
    assert (
        "Exact examples in Expected behavior are mandatory acceptance criteria"
        in provider.last_request.prompt
    )
    assert (
        "The proposed new_content must satisfy the Verification command"
        in provider.last_request.prompt
    )
    assert (
        "Do not use a plausible generic fix if it violates an exact expected output"
        in provider.last_request.prompt
    )
    assert (
        "After JSON parsing, new_content must be normal source text with normal quotes"
        in provider.last_request.prompt
    )
    assert (
        "Do not include literal backslash-escaped quote characters in source code unless they already exist"
        in provider.last_request.prompt
    )
    assert (
        "Do not call a helper that re-acquires a non-reentrant lock while inside that lock"
        in provider.last_request.prompt
    )


def _json_payload_text() -> str:
    import json as json_module

    payload = {
        "target_file": "calculator.py",
        "new_content": "def add(a, b):\n    return a + b\n",
        "rationale": "fix sign",
        "evidence_ids": ["cand-1"],
        "risk_flags": [],
    }
    return json_module.dumps(payload)


def test_parse_provider_edit_response_handles_prose_wrapped_json() -> None:
    json_text = _json_payload_text()
    result = parse_provider_edit_response(f"Here is the fix:\n{json_text}\nHope this helps!")
    assert result.target_file == "calculator.py"
    assert "return a + b" in result.new_content


def test_parse_provider_edit_response_handles_fence_in_middle_of_prose() -> None:
    json_text = _json_payload_text()
    result = parse_provider_edit_response(
        "The fix is:\n```json\n" + json_text + "\n```\nThat should do it."
    )
    assert result.target_file == "calculator.py"
    assert "return a + b" in result.new_content


def test_parse_provider_edit_response_handles_braces_in_trailing_prose() -> None:
    json_text = _json_payload_text()
    result = parse_provider_edit_response(
        json_text + "\n(I verified it with pytest {and} the suite passes.)"
    )
    assert result.target_file == "calculator.py"
    assert "return a + b" in result.new_content


def test_parse_provider_edit_response_handles_bare_json_object_in_prose() -> None:
    json_text = _json_payload_text()
    result = parse_provider_edit_response(f"Before: everything was broken. {json_text}")
    assert result.target_file == "calculator.py"
    assert "return a + b" in result.new_content


def test_provider_backed_edit_proposer_accepts_markdown_fenced_json_response() -> None:
    provider = FakeProvider(
        response_text=(
            "```json\n"
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use addition.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
            "\n```"
        )
    )

    result = ProviderBackedEditProposer(provider=provider).propose(proposal_request())

    assert result.ok is True
    assert result.output is not None
    assert result.output.target_file == "calculator.py"
    assert "return a + b" in result.output.new_content


def test_provider_backed_edit_proposer_includes_repair_context_in_prompt() -> None:
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Repair verification failure.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    request = EditProposalRequest(
        task_id="task-1",
        target_file="calculator.py",
        intent="fix add",
        expected_behavior="add returns a sum",
        current_content="def add(a, b):\n    return a - b\n",
        evidence_ids=("cand-1",),
        allowed_file_paths=("calculator.py",),
        verification_summary="pytest . -q",
        repair_context="Previous verification failed with exit_code=1.",
    )

    result = ProviderBackedEditProposer(provider=provider).propose(request)

    assert result.ok is True
    assert provider.last_request is not None
    assert "Repair context: Previous verification failed with exit_code=1." in (
        provider.last_request.prompt
    )


def test_provider_backed_edit_proposer_persists_prompt_and_response_artifacts(
    tmp_path: Path,
) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / "runs")
    manager.create_run("run-1", {"test": "provider artifacts"})
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use addition.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    proposer = ProviderBackedEditProposer(provider=provider, artifact_manager=manager)

    result = proposer.propose(proposal_request())

    assert result.ok is True
    artifact_paths = {artifact.path for artifact in result.artifacts}
    assert "runs/run-1/provider/task-1/prompt.txt" in artifact_paths
    assert "runs/run-1/provider/task-1/response.txt" in artifact_paths
    prompt_text = (
        tmp_path / "runs" / "run-1" / "provider" / "task-1" / "prompt.txt"
    ).read_text(encoding="utf-8")
    response_text = (
        tmp_path / "runs" / "run-1" / "provider" / "task-1" / "response.txt"
    ).read_text(encoding="utf-8")
    assert "Expected behavior: add returns a sum" in prompt_text
    assert '"target_file":"calculator.py"' in response_text


def test_provider_backed_edit_proposer_includes_evidence_context_in_prompt() -> None:
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use evidence.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    request = EditProposalRequest(
        task_id="task-1",
        target_file="calculator.py",
        intent="fix add",
        expected_behavior="add returns a sum",
        current_content="def add(a, b):\n    return a - b\n",
        evidence_ids=("cand-1",),
        allowed_file_paths=("calculator.py",),
        verification_summary="pytest . -q",
        evidence_context=(
            EditProposalEvidenceContext(
                evidence_id="cand-1",
                file_path="calculator.py",
                span_start=1,
                span_end=2,
                content="retrieved evidence says add currently subtracts",
            ),
        ),
    )

    result = ProviderBackedEditProposer(provider=provider).propose(request)

    assert result.ok is True
    assert provider.last_request is not None
    assert "Evidence context:" in provider.last_request.prompt
    assert "[cand-1] calculator.py:1-2" in provider.last_request.prompt
    assert "retrieved evidence says add currently subtracts" in provider.last_request.prompt


def test_provider_backed_edit_proposer_truncates_long_evidence_context_items() -> None:
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use evidence.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    request = EditProposalRequest(
        task_id="task-1",
        target_file="calculator.py",
        intent="fix add",
        expected_behavior="add returns a sum",
        current_content="def add(a, b):\n    return a - b\n",
        evidence_ids=("cand-1",),
        allowed_file_paths=("calculator.py",),
        verification_summary="pytest . -q",
        evidence_context=(
            EditProposalEvidenceContext(
                evidence_id="cand-1",
                file_path="calculator.py",
                span_start=1,
                span_end=2,
                content="abcdefghij",
            ),
        ),
    )

    result = ProviderBackedEditProposer(
        provider=provider,
        max_evidence_item_chars=4,
        max_evidence_context_chars=20,
    ).propose(request)

    assert result.ok is True
    assert provider.last_request is not None
    assert "abcd\n[truncated]" in provider.last_request.prompt
    assert "abcdefghij" not in provider.last_request.prompt


def test_provider_backed_edit_proposer_limits_total_evidence_context_chars() -> None:
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use evidence.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    request = EditProposalRequest(
        task_id="task-1",
        target_file="calculator.py",
        intent="fix add",
        expected_behavior="add returns a sum",
        current_content="def add(a, b):\n    return a - b\n",
        evidence_ids=("cand-1", "cand-2"),
        allowed_file_paths=("calculator.py",),
        verification_summary="pytest . -q",
        evidence_context=(
            EditProposalEvidenceContext(
                evidence_id="cand-1",
                file_path="calculator.py",
                span_start=1,
                span_end=2,
                content="first evidence",
            ),
            EditProposalEvidenceContext(
                evidence_id="cand-2",
                file_path="calculator.py",
                span_start=3,
                span_end=4,
                content="second evidence",
            ),
        ),
    )

    result = ProviderBackedEditProposer(
        provider=provider,
        max_evidence_item_chars=100,
        max_evidence_context_chars=5,
    ).propose(request)

    assert result.ok is True
    assert provider.last_request is not None
    assert "first" in provider.last_request.prompt
    assert "second evidence" not in provider.last_request.prompt
    assert "[evidence context budget exhausted]" in provider.last_request.prompt


def test_provider_backed_edit_proposer_reports_prompt_metadata_in_telemetry() -> None:
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use evidence.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    request = EditProposalRequest(
        task_id="task-1",
        target_file="calculator.py",
        intent="fix add",
        expected_behavior="add returns a sum",
        current_content="def add(a, b):\n    return a - b\n",
        evidence_ids=("cand-1",),
        allowed_file_paths=("calculator.py",),
        verification_summary="pytest . -q",
        evidence_context=(
            EditProposalEvidenceContext(
                evidence_id="cand-1",
                file_path="calculator.py",
                span_start=1,
                span_end=2,
                content="abc",
            ),
        ),
    )

    result = ProviderBackedEditProposer(provider=provider).propose(request)

    assert result.ok is True
    assert result.telemetry.output_summary["prompt_char_count"] > 0
    assert result.telemetry.output_summary["evidence_context_item_count"] == 1
    assert result.telemetry.output_summary["evidence_context_rendered_char_count"] == 3
    assert result.telemetry.output_summary["evidence_context_truncated"] is False


def test_provider_backed_edit_proposer_reports_evidence_context_truncation() -> None:
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use evidence.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    request = EditProposalRequest(
        task_id="task-1",
        target_file="calculator.py",
        intent="fix add",
        expected_behavior="add returns a sum",
        current_content="def add(a, b):\n    return a - b\n",
        evidence_ids=("cand-1",),
        allowed_file_paths=("calculator.py",),
        verification_summary="pytest . -q",
        evidence_context=(
            EditProposalEvidenceContext(
                evidence_id="cand-1",
                file_path="calculator.py",
                span_start=1,
                span_end=2,
                content="abcdefghij",
            ),
        ),
    )

    result = ProviderBackedEditProposer(
        provider=provider,
        max_evidence_item_chars=4,
        max_evidence_context_chars=20,
    ).propose(request)

    assert result.ok is True
    assert result.telemetry.output_summary["evidence_context_rendered_char_count"] == 4
    assert result.telemetry.output_summary["evidence_context_truncated"] is True


def test_provider_backed_edit_proposer_truncates_current_content_to_fit_budget() -> None:
    # A real-repo target file can exceed max_prompt_chars. The proposer must
    # degrade gracefully: rebuild the prompt with a head+tail slice of the
    # file (marked in the prompt and telemetry) instead of hard-failing the
    # case before the provider is ever called.
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Use evidence.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )
    lines = [f"line_{index:04d} = {index * 7}" for index in range(400)]
    current_content = "\n".join(lines) + "\n"
    request = EditProposalRequest(
        task_id="task-1",
        target_file="calculator.py",
        intent="fix add",
        expected_behavior="add returns a sum",
        current_content=current_content,
        evidence_ids=("cand-1",),
        allowed_file_paths=("calculator.py",),
        verification_summary="pytest . -q",
    )

    result = ProviderBackedEditProposer(
        provider=provider,
        max_prompt_chars=5000,
    ).propose(request)

    assert result.ok is True
    assert provider.last_request is not None
    prompt = provider.last_request.prompt
    assert len(prompt) <= 5000
    assert "lines omitted" in prompt
    assert "line_0000 = 0" in prompt
    assert "line_0399 = 2793" in prompt
    assert result.telemetry.output_summary["current_content_truncated"] is True
    assert result.telemetry.output_summary["current_content_char_count"] == len(
        current_content
    )


def test_provider_backed_edit_proposer_rejects_prompt_over_size_limit_without_calling_provider() -> None:
    provider = FakeProvider(
        response_text=(
            '{"target_file":"calculator.py",'
            '"new_content":"def add(a, b):\\n    return a + b\\n",'
            '"rationale":"Should not be called.",'
            '"evidence_ids":["cand-1"],'
            '"risk_flags":[]}'
        )
    )

    result = ProviderBackedEditProposer(
        provider=provider,
        max_prompt_chars=10,
    ).propose(proposal_request())

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "provider_prompt_budget_exceeded"
    assert provider.last_request is None
    assert result.error.details["max_prompt_chars"] == 10
    assert result.error.details["prompt_char_count"] > 10
    assert result.telemetry.output_summary["prompt_char_count"] > 10
    assert result.telemetry.output_summary["current_content_truncated"] is False


def test_provider_backed_edit_proposer_rejects_invalid_json() -> None:
    proposer = ProviderBackedEditProposer(provider=FakeProvider("not json"))

    result = proposer.propose(proposal_request())

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "provider_response_invalid"


def test_provider_backed_edit_proposer_reports_truncated_response_separately() -> None:
    proposer = ProviderBackedEditProposer(
        provider=FakeProvider(
            response_text='{"target_file":"calculator.py","new_content":"def',
            metadata={"finish_reason": "max_tokens"},
        )
    )

    result = proposer.propose(proposal_request())

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "provider_response_truncated"
    assert result.error.details["finish_reason"] == "max_tokens"


def test_provider_backed_edit_proposer_repairs_unescaped_backslashes_in_json() -> None:
    # Model emitted a literal backslash (e.g. r'%s^{\dagger}') without
    # escaping it inside the JSON string: json.loads rejects \d as an invalid
    # escape. The parser must repair it (\d -> \\d) and still recover the
    # full file content. Build the valid JSON first, then corrupt it exactly
    # the way the model does (drop one backslash before 'dagger').
    import json as json_module

    payload = {
        "target_file": "calculator.py",
        "new_content": "tex = r'%s^{\\dagger}' % arg\nif exp:\n    pass",
        "rationale": "fix",
        "evidence_ids": ["cand-1"],
        "risk_flags": [],
    }
    valid = json_module.dumps(payload)
    response_text = valid.replace("\\\\dagger", "\\dagger")
    with pytest.raises(json_module.JSONDecodeError):
        json_module.loads(response_text)

    proposer = ProviderBackedEditProposer(provider=FakeProvider(response_text))

    result = proposer.propose(proposal_request())

    assert result.ok is True
    assert result.output is not None
    assert result.output.target_file == "calculator.py"
    assert "dagger" in result.output.new_content
    assert "\\d" in result.output.new_content
    assert "if exp:" in result.output.new_content


def test_provider_backed_edit_proposer_reports_provider_invocation_failure() -> None:
    class RaisingProvider:
        def propose_edit(self, request: ProviderEditProposalRequest):
            raise OSError("dns lookup failed")

    result = ProviderBackedEditProposer(provider=RaisingProvider()).propose(
        proposal_request()
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "provider_invocation_failed"
    assert result.error.retryable is True
    assert "dns lookup failed" in result.error.message
    assert result.telemetry.token_usage == {}


def test_provider_backed_edit_proposer_rejects_missing_required_key() -> None:
    proposer = ProviderBackedEditProposer(
        provider=FakeProvider('{"target_file":"calculator.py"}')
    )

    result = proposer.propose(proposal_request())

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "provider_response_invalid"


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


def _diff_mode_request() -> EditProposalRequest:
    return EditProposalRequest(
        task_id="task-1",
        target_file="calculator.py",
        intent="fix add",
        expected_behavior="add returns a sum",
        current_content="def add(a, b):\n    return a - b\n",
        evidence_ids=("cand-1",),
        allowed_file_paths=("calculator.py",),
        verification_summary="pytest . -q",
        proposal_mode="unified_diff",
    )


def _diff_payload_text() -> str:
    import json as json_module

    diff_text = (
        "--- a/calculator.py\n"
        "+++ b/calculator.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
    )
    payload = {
        "target_file": "calculator.py",
        "rationale": "fix sign via diff",
        "evidence_ids": ["cand-1"],
        "risk_flags": [],
    }
    return (
        "```json\n"
        + json_module.dumps(payload)
        + "\n```\n```diff\n"
        + diff_text
        + "```"
    )


def test_diff_mode_prompt_requests_unified_diff() -> None:
    provider = FakeProvider(_diff_payload_text())

    ProviderBackedEditProposer(provider=provider).propose(_diff_mode_request())

    assert provider.last_request is not None
    prompt = provider.last_request.prompt
    assert (
        "Return a JSON object with keys: target_file, rationale, evidence_ids, risk_flags inside a ```json fence."
        in prompt
    )
    assert (
        "Then return the unified diff inside a separate ```diff fence, with NO JSON escaping of the diff."
        in prompt
    )
    assert "diff must be a unified diff against the Current content section below." in prompt
    assert "@@ -old_start,old_count +new_start,new_count @@" in prompt
    assert "Make the smallest set of hunks that fixes the bug" in prompt
    assert (
        "new_content must be the complete replacement content for the entire target file"
        not in prompt
    )
    assert "Do not return a snippet, diff, patch, or partial function body" not in prompt


def test_diff_mode_applies_provider_diff() -> None:
    proposer = ProviderBackedEditProposer(provider=FakeProvider(_diff_payload_text()))

    result = proposer.propose(_diff_mode_request())

    assert result.ok is True
    assert result.output is not None
    assert result.output.new_content == "def add(a, b):\n    return a + b\n"
    assert result.output.diff is not None
    assert "+    return a + b" in result.output.diff


def test_diff_mode_accepts_unescaped_diff_fence_with_quotes() -> None:
    # The live milestone failure: models cannot be trusted to JSON-escape a
    # code diff (raw quotes and newlines inside the JSON string broke
    # parsing). The ```diff fence must carry the diff raw.
    import json as json_module

    diff_text = (
        "--- a/calculator.py\n"
        "+++ b/calculator.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        '-    return "a" - b\n'
        '+    return "a" + b\n'
    )
    payload = {
        "target_file": "calculator.py",
        "rationale": "raw fence diff",
        "evidence_ids": ["cand-1"],
        "risk_flags": [],
    }
    response = (
        "```json\n"
        + json_module.dumps(payload)
        + "\n```\n```diff\n"
        + diff_text
        + "```"
    )
    request = EditProposalRequest(
        task_id="task-1",
        target_file="calculator.py",
        intent="fix add",
        expected_behavior="add returns a sum",
        current_content='def add(a, b):\n    return "a" - b\n',
        evidence_ids=("cand-1",),
        allowed_file_paths=("calculator.py",),
        verification_summary="pytest . -q",
        proposal_mode="unified_diff",
    )

    result = ProviderBackedEditProposer(provider=FakeProvider(response)).propose(request)

    assert result.ok is True
    assert result.output is not None
    assert result.output.new_content == 'def add(a, b):\n    return "a" + b\n'


def test_diff_mode_accepts_full_new_content_fallback() -> None:
    import json as json_module

    payload = {
        "target_file": "calculator.py",
        "new_content": "def add(a, b):\n    return a + b\n",
        "rationale": "fallback to full content",
        "evidence_ids": ["cand-1"],
        "risk_flags": [],
    }
    proposer = ProviderBackedEditProposer(
        provider=FakeProvider(json_module.dumps(payload))
    )

    result = proposer.propose(_diff_mode_request())

    assert result.ok is True
    assert result.output is not None
    assert result.output.new_content == "def add(a, b):\n    return a + b\n"
    assert result.output.diff is None


def test_diff_mode_reports_unapplicable_diff_as_retryable() -> None:
    import json as json_module

    # The hunk context does not match the current content (wrong function
    # name), so the tolerant applier must reject it loudly instead of
    # corrupting the file silently.
    diff_text = (
        "--- a/calculator.py\n"
        "+++ b/calculator.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def subtract(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
    )
    payload = {
        "target_file": "calculator.py",
        "diff": diff_text,
        "rationale": "wrong context",
        "evidence_ids": ["cand-1"],
        "risk_flags": [],
    }
    proposer = ProviderBackedEditProposer(
        provider=FakeProvider(json_module.dumps(payload))
    )

    result = proposer.propose(_diff_mode_request())

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "provider_diff_not_applicable"
    assert result.error.retryable is True
    assert "hunk_context_mismatch" in result.error.message


def test_parse_provider_edit_response_diff_mode_requires_diff_or_new_content() -> None:
    with pytest.raises(ValueError):
        parse_provider_edit_response(
            '{"target_file":"calculator.py",'
            '"rationale":"x",'
            '"evidence_ids":[],'
            '"risk_flags":[]}',
            mode="unified_diff",
        )


def test_parse_provider_edit_response_repairs_raw_newlines_in_diff() -> None:
    diff = "--- a/calculator.py\n+++ b/calculator.py\n@@ -1,1 +1,2 @@\n-old\n+new"
    raw = (
        '```json\n{\n  "target_file": "calculator.py",\n'
        '  "diff": "' + diff + '",\n'
        '  "rationale": "x",\n  "evidence_ids": [],\n  "risk_flags": []\n}\n```'
    )
    result = parse_provider_edit_response(raw, mode="unified_diff")
    assert result.diff == diff


def test_proposer_persists_per_attempt_artifacts(tmp_path: Path) -> None:
    manager = ArtifactManager(workspace_root=tmp_path, artifact_root=tmp_path / "runs")
    manager.create_run("run-1", {"test": "per-attempt artifacts"})
    provider = FakeProvider(_diff_payload_text())
    proposer = ProviderBackedEditProposer(provider=provider, artifact_manager=manager)

    proposer.propose(_diff_mode_request())
    proposer.propose(_diff_mode_request())

    expected_paths = (
        "runs/run-1/provider/task-1/prompt.txt",
        "runs/run-1/provider/task-1/response.txt",
        "runs/run-1/provider/task-1/attempt_0/prompt.txt",
        "runs/run-1/provider/task-1/attempt_0/response.txt",
        "runs/run-1/provider/task-1/attempt_1/prompt.txt",
        "runs/run-1/provider/task-1/attempt_1/response.txt",
    )
    for path in expected_paths:
        assert (tmp_path / path).is_file(), f"missing artifact: {path}"
