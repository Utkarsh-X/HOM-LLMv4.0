"""OpenAI provider implementation.

API Key Configuration:
    Priority order (first found wins):
    1. Explicit api_key parameter passed to __init__
    2. configs/secrets.yaml file (api_keys.openai)
    3. OPENAI_API_KEY environment variable
"""

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from homllm.generation.interfaces import (
    ProviderCapabilities,
    ProviderConnector,
    ProviderRequest,
    ProviderResponse,
)

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
    logger.warning("openai not available, OpenAIProvider disabled")


def _load_api_key_from_config(provider_name: str = "openai") -> Optional[str]:
    """
    Load API key from configs/secrets.yaml.
    
    Args:
        provider_name: Key name under api_keys section (e.g., 'gemini', 'openai')
    
    Returns:
        API key string if found, None otherwise
    """
    try:
        import yaml
    except ImportError:
        logger.debug("PyYAML not installed; cannot read secrets.yaml")
        return None
    
    # Search for secrets.yaml relative to project root
    search_paths = [
        Path(__file__).resolve().parent.parent.parent.parent.parent / "configs" / "secrets.yaml",
        Path.cwd() / "configs" / "secrets.yaml",
    ]
    
    for secrets_path in search_paths:
        if secrets_path.exists():
            try:
                with open(secrets_path, "r", encoding="utf-8") as f:
                    secrets = yaml.safe_load(f)
                
                if secrets and "api_keys" in secrets:
                    api_key = secrets["api_keys"].get(provider_name)
                    if api_key and api_key != f"your_{provider_name}_api_key_here":
                        logger.debug(f"Loaded {provider_name} API key from {secrets_path}")
                        return api_key
            except Exception as e:
                logger.debug(f"Failed to load secrets from {secrets_path}: {e}")
    
    return None


class OpenAIProvider(ProviderConnector):
    """OpenAI provider implementation."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        Initialize OpenAI provider.
        
        Args:
            api_key: OpenAI API key. If not provided, looks for key in:
                     1. configs/secrets.yaml (api_keys.openai)
                     2. OPENAI_API_KEY environment variable
            base_url: Custom base URL (for proxies)
        """
        self.base_url = base_url
        self._client: Optional[OpenAI] = None
        self._available = False

        if OpenAI is not None:
            try:
                # Priority: explicit param > config file > env var
                resolved_key = api_key
                
                if not resolved_key:
                    # Try loading from config file
                    resolved_key = _load_api_key_from_config("openai")
                    if resolved_key:
                        logger.info("Using OpenAI API key from configs/secrets.yaml")
                
                self.api_key = resolved_key
                self._client = OpenAI(api_key=resolved_key, base_url=base_url)
                self._available = self.healthcheck()
            except Exception as e:
                logger.warning(f"OpenAI provider unavailable: {e}")

    def invoke_sync(self, request: ProviderRequest) -> ProviderResponse:
        """Synchronous invocation."""
        if not self._available or self._client is None:
            raise RuntimeError("OpenAI provider not available")

        try:
            start_time = time.time()

            # Prepare request
            messages = [{"role": "user", "content": request.prompt}]

            kwargs = {
                "model": request.model,
                "messages": messages,
                "temperature": request.config.temperature,
                "max_tokens": request.config.max_output_tokens,
            }

            if request.config.seed is not None:
                kwargs["seed"] = request.config.seed

            if request.config.top_p is not None:
                kwargs["top_p"] = request.config.top_p

            # Invoke API
            response = self._client.chat.completions.create(**kwargs)

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract response
            choice = response.choices[0]
            text = choice.message.content or ""
            tokens_in = response.usage.prompt_tokens if response.usage else 0
            tokens_out = response.usage.completion_tokens if response.usage else 0
            finish_reason = choice.finish_reason or "stop"

            return ProviderResponse(
                text=text,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                finish_reason=finish_reason,
                model=request.model,
                metadata={"response": response.model_dump()},
            )

        except Exception as e:
            logger.error(f"OpenAI provider invocation failed: {e}")
            raise

    def invoke_stream(
        self, request: ProviderRequest, on_chunk: Callable[[str], None]
    ) -> ProviderResponse:
        """Streaming invocation."""
        if not self._available or self._client is None:
            raise RuntimeError("OpenAI provider not available")

        try:
            messages = [{"role": "user", "content": request.prompt}]

            kwargs = {
                "model": request.model,
                "messages": messages,
                "temperature": request.config.temperature,
                "max_tokens": request.config.max_output_tokens,
                "stream": True,
            }

            if request.config.seed is not None:
                kwargs["seed"] = request.config.seed

            # Stream response
            full_text = ""
            for chunk in self._client.chat.completions.create(**kwargs):
                if chunk.choices[0].delta.content:
                    chunk_text = chunk.choices[0].delta.content
                    full_text += chunk_text
                    on_chunk(chunk_text)

            # Estimate tokens (OpenAI doesn't provide usage in streaming)
            tokens_in = len(request.prompt.split()) * 1.3  # Rough estimate
            tokens_out = len(full_text.split()) * 1.3

            return ProviderResponse(
                text=full_text,
                tokens_in=int(tokens_in),
                tokens_out=int(tokens_out),
                finish_reason="stop",
                model=request.model,
                metadata={},
            )

        except Exception as e:
            logger.error(f"OpenAI provider streaming failed: {e}")
            raise

    def healthcheck(self) -> bool:
        """Check if provider is available."""
        if self._client is None:
            return False

        try:
            # Try a minimal request
            self._client.models.list()
            return True
        except Exception:
            return False

    def capabilities(self) -> ProviderCapabilities:
        """Returns provider capabilities."""
        return ProviderCapabilities(
            streaming=True,
            max_tokens=4096,  # Varies by model
            rate_limits={"requests_per_minute": 60, "tokens_per_minute": 90000},
            supports_seed=True,
            supports_json_mode=True,
        )
