from collections.abc import Callable

from homllm.generation.interfaces import (
    ModelConfig,
    ProviderCapabilities,
    ProviderRequest,
    ProviderResponse,
)
from homllm_v4.adapters.v3_provider_edit_proposer import V3ProviderEditProposalAdapter
from homllm_v4.contracts.edit_proposal import EditProposalRequest
from homllm_v4.planning.provider_edit_proposer import (
    ProviderBackedEditProposer,
    ProviderEditProposalRequest,
)


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
