"""Google Gemini provider implementation.

Uses the new Google GenAI SDK (google.genai) which replaces the deprecated
google.generativeai package.
"""

import logging
import os
import time
from collections.abc import Callable
from typing import Optional

from homllm.generation.interfaces import (
    ProviderCapabilities,
    ProviderConnector,
    ProviderRequest,
    ProviderResponse,
)

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None
    logger.debug("google.genai not available; GeminiProvider disabled")


class GeminiProvider(ProviderConnector):
    """Google Gemini provider implementation using the new GenAI SDK."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Gemini provider.
        
        Args:
            api_key: Gemini API key (default: from GEMINI_API_KEY env var)
        """
        self._client: Optional[object] = None
        self._available = False

        if genai is not None:
            try:
                # New SDK uses Client object
                # It will auto-read GEMINI_API_KEY from environment if not provided
                if api_key:
                    self._client = genai.Client(api_key=api_key)
                else:
                    self._client = genai.Client()
                
                self._available = self.healthcheck()
                if self._available:
                    logger.info("Gemini provider initialized (new GenAI SDK)")
            except Exception as e:
                logger.debug(f"Gemini provider unavailable: {e}")

    def invoke_sync(self, request: ProviderRequest) -> ProviderResponse:
        """Synchronous invocation."""
        if not self._available or self._client is None:
            raise RuntimeError("Gemini provider not available")

        try:
            start_time = time.time()

            # Build generation config using new SDK types
            config_dict = {
                "temperature": request.config.temperature,
                "max_output_tokens": request.config.max_output_tokens,
            }

            if request.config.top_p is not None:
                config_dict["top_p"] = request.config.top_p

            if request.config.top_k is not None:
                config_dict["top_k"] = request.config.top_k

            # Debug log the config being sent
            logger.info(f"[GEMINI_CONFIG] max_output_tokens={config_dict.get('max_output_tokens')}, temp={config_dict.get('temperature')}")

            # Invoke API using new SDK pattern
            response = self._client.models.generate_content(
                model=request.model,
                contents=request.prompt,
                config=config_dict,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract response text
            text = response.text if response.text else ""
            
            # Extract token counts from usage_metadata
            tokens_in = 0
            tokens_out = 0
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                tokens_in = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
                tokens_out = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0

            # Extract finish_reason
            finish_reason = "unknown"
            if response.candidates:
                raw_reason = response.candidates[0].finish_reason
                # In new SDK, finish_reason is typically a string or enum
                if hasattr(raw_reason, 'name'):
                    finish_reason = raw_reason.name.lower()
                elif hasattr(raw_reason, 'value'):
                    reason_value = raw_reason.value
                    reason_map = {
                        1: "stop",
                        2: "max_tokens",
                        3: "safety",
                        4: "recitation",
                        5: "other",
                    }
                    finish_reason = reason_map.get(reason_value, f"unknown_{reason_value}")
                else:
                    finish_reason = str(raw_reason).lower() if raw_reason else "stop"
                
                # Log non-stop finish reasons for debugging
                if finish_reason not in ("stop", "finish_reason_stop"):
                    logger.warning(f"Gemini finish_reason: {finish_reason} (tokens_out={tokens_out})")

            return ProviderResponse(
                text=text,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                finish_reason=finish_reason,
                model=request.model,
                metadata={"latency_ms": latency_ms},
            )

        except Exception as e:
            logger.error(f"Gemini provider invocation failed: {e}")
            raise

    def invoke_stream(
        self, request: ProviderRequest, on_chunk: Callable[[str], None]
    ) -> ProviderResponse:
        """Streaming invocation."""
        if not self._available or self._client is None:
            raise RuntimeError("Gemini provider not available")

        try:
            start_time = time.time()
            
            # Build generation config
            config_dict = {
                "temperature": request.config.temperature,
                "max_output_tokens": request.config.max_output_tokens,
            }

            # Stream response using new SDK
            full_text = ""
            for chunk in self._client.models.generate_content_stream(
                model=request.model,
                contents=request.prompt,
                config=config_dict,
            ):
                if chunk.text:
                    full_text += chunk.text
                    on_chunk(chunk.text)

            latency_ms = int((time.time() - start_time) * 1000)

            # Estimate tokens for streaming (no usage_metadata in stream)
            tokens_in = int(len(request.prompt.split()) * 1.3)
            tokens_out = int(len(full_text.split()) * 1.3)

            return ProviderResponse(
                text=full_text,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                finish_reason="stop",
                model=request.model,
                metadata={"latency_ms": latency_ms},
            )

        except Exception as e:
            logger.error(f"Gemini provider streaming failed: {e}")
            raise

    def healthcheck(self) -> bool:
        """Check if provider is available."""
        if self._client is None:
            return False

        try:
            # Try to list models using new SDK
            list(self._client.models.list())
            return True
        except Exception:
            return False

    def capabilities(self) -> ProviderCapabilities:
        """Returns provider capabilities."""
        return ProviderCapabilities(
            streaming=True,
            max_tokens=8192,  # Varies by model
            rate_limits={"requests_per_minute": 60, "tokens_per_minute": 1000000},
            supports_seed=True,  # New SDK supports seed
            supports_json_mode=True,  # New SDK supports JSON mode
        )
