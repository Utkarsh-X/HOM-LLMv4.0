from homllm.generation.interfaces import ModelConfig, ProviderConnector
from homllm.generation.providers import GeminiProvider, OpenAIProvider
from homllm_v4.adapters.v3_provider_edit_proposer import V3ProviderEditProposalAdapter


def build_v3_provider_edit_adapter(
    *,
    provider_name: str,
    model: str,
    model_config: ModelConfig,
    api_key: str | None = None,
    gemini_provider_cls: type[ProviderConnector] = GeminiProvider,
    openai_provider_cls: type[ProviderConnector] = OpenAIProvider,
) -> V3ProviderEditProposalAdapter:
    normalized = provider_name.lower().strip()
    if normalized == "gemini":
        provider = gemini_provider_cls(api_key=api_key)
    elif normalized == "openai":
        provider = openai_provider_cls(api_key=api_key)
    elif normalized == "openrouter":
        # OpenRouter exposes an OpenAI-compatible chat-completions API.
        provider = openai_provider_cls(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
    else:
        raise ValueError(f"unsupported provider for edit proposals: {provider_name}")

    return V3ProviderEditProposalAdapter(
        provider=provider,
        model=model,
        model_config=model_config,
    )


def build_v3_provider_edit_adapter_from_params(
    *,
    provider_name: str,
    model: str,
    api_key: str | None = None,
    temperature: float = 0.0,
    max_output_tokens: int = 2048,
    gemini_provider_cls: type[ProviderConnector] = GeminiProvider,
    openai_provider_cls: type[ProviderConnector] = OpenAIProvider,
) -> V3ProviderEditProposalAdapter:
    return build_v3_provider_edit_adapter(
        provider_name=provider_name,
        model=model,
        model_config=ModelConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ),
        api_key=api_key,
        gemini_provider_cls=gemini_provider_cls,
        openai_provider_cls=openai_provider_cls,
    )
