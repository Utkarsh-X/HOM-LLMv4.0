"""Determinism tests for Generation layer."""

import pytest

from homllm.common.types import Intent
from homllm.context.interfaces import ContextArtifact, ContextBlock
from homllm.generation.adapter import GenerationAdapter
from homllm.generation.interfaces import GenerationRequest, ModelConfig
from homllm.generation.providers.local import LocalProvider


@pytest.fixture
def test_context_artifact() -> ContextArtifact:
    """Create test context artifact."""
    blocks = [
        ContextBlock(
            block_id="block1",
            file="test.py",
            start_line=1,
            end_line=10,
            content="def test():\n    pass\n",
            symbol_id="test",
            symbol_name="test",
            provenance=("bm25",),
        ),
    ]

    return ContextArtifact(
        query_id="test-query",
        context_text="def test():\n    pass\n",
        blocks=tuple(blocks),
        token_budget=1000,
        used_tokens=50,
        provenance={},
        explain_trace=tuple(["Selected 1 block"]),
    )


@pytest.fixture
def test_model_config() -> ModelConfig:
    """Create test model configuration."""
    return ModelConfig(
        temperature=0.0,  # Deterministic
        max_output_tokens=100,
        seed=42,  # Fixed seed for determinism
    )


def test_generation_raw_text_persistence(
    test_context_artifact: ContextArtifact, test_model_config: ModelConfig
):
    """
    Test that raw text is always persisted before parsing.
    
    GEN-005: Raw response always persisted before parsing
    """
    # Create a mock provider that returns text
    class MockProvider:
        def invoke_sync(self, request):
            from homllm.generation.interfaces import ProviderResponse

            return ProviderResponse(
                text='{"result": "test"}',
                tokens_in=10,
                tokens_out=5,
                finish_reason="stop",
                model="test-model",
                metadata={},
            )

        def healthcheck(self):
            return True

        def capabilities(self):
            from homllm.generation.interfaces import ProviderCapabilities

            return ProviderCapabilities(
                streaming=False,
                max_tokens=1000,
                rate_limits={},
                supports_seed=True,
                supports_json_mode=True,
            )

    provider = MockProvider()
    adapter = GenerationAdapter(provider)

    request = GenerationRequest(
        request_id="test-1",
        query="test query",
        intent=Intent.EXPLAIN,
        context_artifact=test_context_artifact,
        prompt_template="explain",
        template_variables={},
        output_mode="STRUCTURED",
        model_config=test_model_config,
    )

    result = adapter.generate(request)

    # Raw text must be present
    assert result.raw_text is not None
    assert len(result.raw_text) > 0

    # Raw text should be stored before parsing
    assert result.raw_text == '{"result": "test"}'


def test_generation_does_not_modify_context(
    test_context_artifact: ContextArtifact, test_model_config: ModelConfig
):
    """
    Test that generation does not modify context artifact.
    
    GEN-002: Does not modify context artifact
    """
    class MockProvider:
        def invoke_sync(self, request):
            from homllm.generation.interfaces import ProviderResponse

            return ProviderResponse(
                text="test response",
                tokens_in=10,
                tokens_out=5,
                finish_reason="stop",
                model="test-model",
                metadata={},
            )

        def healthcheck(self):
            return True

        def capabilities(self):
            from homllm.generation.interfaces import ProviderCapabilities

            return ProviderCapabilities(
                streaming=False,
                max_tokens=1000,
                rate_limits={},
                supports_seed=True,
                supports_json_mode=False,
            )

    provider = MockProvider()
    adapter = GenerationAdapter(provider)

    # Store original context
    original_blocks = test_context_artifact.blocks
    original_text = test_context_artifact.context_text

    request = GenerationRequest(
        request_id="test-1",
        query="test query",
        intent=Intent.EXPLAIN,
        context_artifact=test_context_artifact,
        prompt_template="explain",
        template_variables={},
        output_mode="TEXT",
        model_config=test_model_config,
    )

    adapter.generate(request)

    # Context should be unchanged
    assert test_context_artifact.blocks == original_blocks
    assert test_context_artifact.context_text == original_text
