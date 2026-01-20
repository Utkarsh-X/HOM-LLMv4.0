"""Generation layer - Phase 5: Provider-agnostic LLM adapter."""

from homllm.generation.interfaces import (
    GenerationRequest,
    GenerationResult,
    ProviderConnector,
    ProviderCapabilities,
    ProviderRequest,
    ProviderResponse,
    ModelConfig,
    Diagnostics,
)
from homllm.generation.adapter import GenerationAdapter

__all__ = [
    "GenerationRequest",
    "GenerationResult",
    "ProviderConnector",
    "ProviderCapabilities",
    "ProviderRequest",
    "ProviderResponse",
    "ModelConfig",
    "Diagnostics",
    "GenerationAdapter",
]
