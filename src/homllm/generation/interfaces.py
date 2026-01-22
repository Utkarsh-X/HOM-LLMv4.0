"""Protocols and interfaces for Generation layer."""

from dataclasses import dataclass
from collections.abc import Callable
from typing import Literal, Optional, Protocol

from homllm.common.types import Intent
from homllm.context.interfaces import ContextArtifact


@dataclass(frozen=True)
class ModelConfig:
    """Model configuration for generation."""

    temperature: float
    max_output_tokens: int
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    seed: Optional[int] = None  # For determinism


@dataclass(frozen=True)
class ProviderCapabilities:
    """Provider capabilities."""

    streaming: bool
    max_tokens: int
    rate_limits: dict[str, int]  # requests_per_minute, tokens_per_minute
    supports_seed: bool
    supports_json_mode: bool


@dataclass
class ProviderRequest:
    """Request to provider."""

    prompt: str
    model: str
    config: ModelConfig
    stream: bool = False


@dataclass
class ProviderResponse:
    """Response from provider."""

    text: str
    tokens_in: int
    tokens_out: int
    finish_reason: str  # "stop", "length", "error"
    model: str
    metadata: dict


@dataclass
class Diagnostics:
    """Diagnostics for generation result."""

    parse_warnings: list[str]
    hallucination_flags: list[str]
    corrections_applied: list[str]


@dataclass
class GenerationRequest:
    """Request for generation."""

    request_id: str
    query: str
    intent: Intent
    context_artifact: ContextArtifact
    prompt_template: str
    template_variables: dict
    output_mode: Literal["TEXT", "STRUCTURED", "TRACE", "EXAMPLE"]
    model_config: ModelConfig


@dataclass
class GenerationResult:
    """Result from generation."""

    request_id: str
    status: Literal["OK", "PARTIAL", "ERROR"]
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    raw_text: str  # ALWAYS persisted before parsing
    parsed_output: Optional[dict]
    diagnostics: Diagnostics
    finish_reason: str = "unknown"  # stop, max_tokens, safety, recitation, etc.


class ProviderConnector(Protocol):
    """Protocol for provider connections."""

    def invoke_sync(self, request: ProviderRequest) -> ProviderResponse:
        """Synchronous invocation."""
        ...

    def invoke_stream(
        self, request: ProviderRequest, on_chunk: Callable[[str], None]
    ) -> ProviderResponse:
        """Streaming invocation."""
        ...

    def healthcheck(self) -> bool:
        """Check if provider is available."""
        ...

    def capabilities(self) -> ProviderCapabilities:
        """Returns: streaming, max_tokens, rate_limits, etc."""
        ...
