import pytest
from dataclasses import dataclass
from pathlib import Path

from homllm_v4.artifacts.manager import ArtifactManager
from homllm_v4.contracts.edit_proposal import EditProposalEvidenceContext, EditProposalRequest
from homllm_v4.planning.provider_edit_proposer import (
    ProviderBackedEditProposer,
    ProviderEditProposalRequest,
    ProviderEditProposalResponse,
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
