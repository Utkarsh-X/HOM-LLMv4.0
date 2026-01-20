"""Google Gemini provider implementation."""

import logging
import time
import warnings
from collections.abc import Callable
from typing import Optional

from homllm.generation.interfaces import (
    ProviderCapabilities,
    ProviderConnector,
    ProviderRequest,
    ProviderResponse,
)

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=FutureWarning, module="google\\.generativeai")

try:
    import google.generativeai as genai
except ImportError:
    genai = None
    logger.debug("google.generativeai not available; GeminiProvider disabled")


class GeminiProvider(ProviderConnector):
    """Google Gemini provider implementation."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Gemini provider.
        
        Args:
            api_key: Gemini API key (default: from env)
        """
        self.api_key = api_key
        self._model: Optional[object] = None
        self._available = False

        if genai is not None:
            try:
                if api_key:
                    genai.configure(api_key=api_key)
                self._available = self.healthcheck()
                if self._available:
                    logger.info("Gemini provider initialized")
            except Exception as e:
                logger.debug(f"Gemini provider unavailable: {e}")

    def invoke_sync(self, request: ProviderRequest) -> ProviderResponse:
        """Synchronous invocation."""
        if not self._available or genai is None:
            raise RuntimeError("Gemini provider not available")

        try:
            start_time = time.time()

            # Get model
            model = genai.GenerativeModel(request.model)

            # Prepare generation config
            generation_config = {
                "temperature": request.config.temperature,
                "max_output_tokens": request.config.max_output_tokens,
            }

            if request.config.top_p is not None:
                generation_config["top_p"] = request.config.top_p

            if request.config.top_k is not None:
                generation_config["top_k"] = request.config.top_k

            # Invoke API
            response = model.generate_content(
                request.prompt,
                generation_config=generation_config,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract response
            text = response.text if response.text else ""
            tokens_in = (
                response.usage_metadata.prompt_token_count
                if response.usage_metadata
                else 0
            )
            tokens_out = (
                response.usage_metadata.candidates_token_count
                if response.usage_metadata
                else 0
            )

            return ProviderResponse(
                text=text,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                finish_reason="stop",
                model=request.model,
                metadata={"response": response},
            )

        except Exception as e:
            logger.error(f"Gemini provider invocation failed: {e}")
            raise

    def invoke_stream(
        self, request: ProviderRequest, on_chunk: Callable[[str], None]
    ) -> ProviderResponse:
        """Streaming invocation."""
        if not self._available or genai is None:
            raise RuntimeError("Gemini provider not available")

        try:
            model = genai.GenerativeModel(request.model)

            generation_config = {
                "temperature": request.config.temperature,
                "max_output_tokens": request.config.max_output_tokens,
            }

            # Stream response
            full_text = ""
            for chunk in model.generate_content(
                request.prompt,
                generation_config=generation_config,
                stream=True,
            ):
                if chunk.text:
                    full_text += chunk.text
                    on_chunk(chunk.text)

            # Estimate tokens
            tokens_in = len(request.prompt.split()) * 1.3
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
            logger.error(f"Gemini provider streaming failed: {e}")
            raise

    def healthcheck(self) -> bool:
        """Check if provider is available."""
        if genai is None:
            return False

        try:
            # Try to list models
            list(genai.list_models())
            return True
        except Exception:
            return False

    def capabilities(self) -> ProviderCapabilities:
        """Returns provider capabilities."""
        return ProviderCapabilities(
            streaming=True,
            max_tokens=8192,  # Varies by model
            rate_limits={"requests_per_minute": 60, "tokens_per_minute": 1000000},
            supports_seed=False,  # Gemini doesn't support seed
            supports_json_mode=False,
        )
