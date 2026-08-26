from collections.abc import Callable

import pytest

from homllm.generation.interfaces import (
    ModelConfig,
    ProviderCapabilities,
    ProviderRequest,
    ProviderResponse,
)
from homllm_v4.adapters.v3_provider_factory import (
    build_v3_provider_edit_adapter,
    build_v3_provider_edit_adapter_from_params,
)
from homllm_v4.contracts.edit_proposal import EditProposalRequest
from homllm_v4.planning.provider_edit_proposer import (
    ProviderBackedEditProposer,
    ProviderEditProposalRequest,
)


class FakeProviderConnector:
    instances: list["FakeProviderConnector"] = []

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self.last_request: ProviderRequest | None = None
        FakeProviderConnector.instances.append(self)

    def invoke_sync(self, request: ProviderRequest) -> ProviderResponse:
        self.last_request = request
        return ProviderResponse(
            text=(
                '{"target_file":"calculator.py",'
                '"new_content":"def add(a, b):\\n    return a + b\\n",'
                '"rationale":"Use addition.",'
                '"evidence_ids":["cand-1"],'
                '"risk_flags":[]}'
            ),
            tokens_in=17,
            tokens_out=11,
            finish_reason="stop",
            model=request.model,
            metadata={"provider": "fake"},
        )

    def invoke_stream(
        self,
        request: ProviderRequest,
        on_chunk: Callable[[str], None],
    ) -> ProviderResponse:
        raise AssertionError("streaming should not be used")

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


def reset_fake_provider_instances() -> None:
    FakeProviderConnector.instances.clear()


def test_factory_builds_gemini_provider_adapter_with_injected_provider_class() -> None:
    reset_fake_provider_instances()
    model_config = ModelConfig(temperature=0.0, max_output_tokens=1024)

    adapter = build_v3_provider_edit_adapter(
        provider_name="gemini",
        model="gemini-test-model",
        model_config=model_config,
        api_key="test-key",
        gemini_provider_cls=FakeProviderConnector,
    )

    assert len(FakeProviderConnector.instances) == 1
    assert FakeProviderConnector.instances[0].api_key == "test-key"
    response = adapter.propose_edit(
        ProviderEditProposalRequest(task_id="task-1", prompt="prompt")
    )
    assert response.model == "gemini-test-model"


def test_factory_builds_openai_provider_adapter_with_injected_provider_class() -> None:
    reset_fake_provider_instances()

    build_v3_provider_edit_adapter(
        provider_name="openai",
        model="openai-test-model",
        model_config=ModelConfig(temperature=0.0, max_output_tokens=1024),
        api_key="openai-key",
        openai_provider_cls=FakeProviderConnector,
    )

    assert len(FakeProviderConnector.instances) == 1
    assert FakeProviderConnector.instances[0].api_key == "openai-key"


def test_factory_rejects_unsupported_provider() -> None:
    with pytest.raises(ValueError, match="unsupported provider"):
        build_v3_provider_edit_adapter(
            provider_name="unknown",
            model="model",
            model_config=ModelConfig(temperature=0.0, max_output_tokens=1024),
        )


def test_factory_adapter_can_drive_provider_backed_edit_proposer() -> None:
    reset_fake_provider_instances()
    adapter = build_v3_provider_edit_adapter(
        provider_name="gemini",
        model="gemini-test-model",
        model_config=ModelConfig(temperature=0.0, max_output_tokens=1024),
        api_key="test-key",
        gemini_provider_cls=FakeProviderConnector,
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
    assert result.telemetry.model_usage["provider"] == "fake"


def test_factory_builds_provider_adapter_from_primitive_params() -> None:
    reset_fake_provider_instances()

    adapter = build_v3_provider_edit_adapter_from_params(
        provider_name="gemini",
        model="gemini-live-test",
        api_key="test-key",
        temperature=0.0,
        max_output_tokens=512,
        gemini_provider_cls=FakeProviderConnector,
    )

    response = adapter.propose_edit(
        ProviderEditProposalRequest(task_id="task-1", prompt="prompt")
    )
    assert response.model == "gemini-live-test"
    assert len(FakeProviderConnector.instances) == 1
    assert FakeProviderConnector.instances[0].api_key == "test-key"


class KwargCapturingConnector(FakeProviderConnector):
    """Same fake behavior, but records every constructor kwarg it receives."""

    def __init__(self, **kwargs) -> None:
        self.constructor_kwargs = dict(kwargs)
        self.api_key = kwargs.get("api_key")
        self.last_request: ProviderRequest | None = None
        FakeProviderConnector.instances.append(self)


def test_factory_openrouter_branch_uses_openai_compatible_base_url() -> None:
    reset_fake_provider_instances()

    adapter = build_v3_provider_edit_adapter(
        provider_name="openrouter",
        model="stealth/ox-alpha",
        model_config=ModelConfig(temperature=0.0, max_output_tokens=1024),
        api_key="or-key",
        openai_provider_cls=KwargCapturingConnector,
    )

    assert len(KwargCapturingConnector.instances) == 1
    constructed = KwargCapturingConnector.instances[0]
    assert constructed.constructor_kwargs == {
        "api_key": "or-key",
        "base_url": "https://openrouter.ai/api/v1",
    }
    response = adapter.propose_edit(
        ProviderEditProposalRequest(task_id="task-1", prompt="prompt")
    )
    assert response.model == "stealth/ox-alpha"


def test_factory_openrouter_name_matching_is_normalized() -> None:
    reset_fake_provider_instances()

    build_v3_provider_edit_adapter(
        provider_name="  OpenRouter ",
        model="model",
        model_config=ModelConfig(temperature=0.0, max_output_tokens=8),
        api_key=None,
        openai_provider_cls=KwargCapturingConnector,
    )

    constructed = KwargCapturingConnector.instances[0]
    assert constructed.constructor_kwargs["base_url"] == "https://openrouter.ai/api/v1"
    assert constructed.api_key is None


def test_factory_openai_branch_does_not_receive_base_url() -> None:
    reset_fake_provider_instances()

    build_v3_provider_edit_adapter(
        provider_name="openai",
        model="model",
        model_config=ModelConfig(temperature=0.0, max_output_tokens=8),
        api_key="oa-key",
        openai_provider_cls=KwargCapturingConnector,
    )

    assert KwargCapturingConnector.instances[0].constructor_kwargs == {"api_key": "oa-key"}


def test_factory_from_params_threads_openrouter_base_url() -> None:
    reset_fake_provider_instances()

    build_v3_provider_edit_adapter_from_params(
        provider_name="openrouter",
        model="stealth/ox-alpha",
        api_key="or-key",
        temperature=0.0,
        max_output_tokens=512,
        openai_provider_cls=KwargCapturingConnector,
    )

    constructed = KwargCapturingConnector.instances[0]
    assert constructed.constructor_kwargs == {
        "api_key": "or-key",
        "base_url": "https://openrouter.ai/api/v1",
    }
