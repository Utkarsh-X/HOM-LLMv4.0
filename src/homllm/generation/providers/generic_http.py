"""Generic HTTP provider implementation."""

import json
import logging
import time
from collections.abc import Callable
from typing import Optional

import requests

from homllm.generation.interfaces import (
    ProviderCapabilities,
    ProviderConnector,
    ProviderRequest,
    ProviderResponse,
)

logger = logging.getLogger(__name__)


class GenericHTTPProvider(ProviderConnector):
    """Generic HTTP provider for custom API endpoints."""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        headers: Optional[dict] = None,
    ):
        """
        Initialize generic HTTP provider.
        
        Args:
            base_url: Base URL for API
            api_key: API key (if required)
            headers: Custom headers
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = headers or {}
        if api_key:
            self.headers.setdefault("Authorization", f"Bearer {api_key}")
        self._available = False

        try:
            self._available = self.healthcheck()
        except Exception as e:
            logger.warning(f"Generic HTTP provider unavailable: {e}")

    def invoke_sync(self, request: ProviderRequest) -> ProviderResponse:
        """Synchronous invocation."""
        if not self._available:
            raise RuntimeError("Generic HTTP provider not available")

        try:
            start_time = time.time()

            # Prepare request payload (OpenAI-compatible format)
            payload = {
                "model": request.model,
                "messages": [{"role": "user", "content": request.prompt}],
                "temperature": request.config.temperature,
                "max_tokens": request.config.max_output_tokens,
            }

            if request.config.seed is not None:
                payload["seed"] = request.config.seed

            # Make request
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=self.headers,
                timeout=180,
            )
            response.raise_for_status()

            latency_ms = int((time.time() - start_time) * 1000)

            # Parse response
            data = response.json()
            choice = data["choices"][0]
            text = choice["message"]["content"] or ""
            tokens_in = data.get("usage", {}).get("prompt_tokens", 0)
            tokens_out = data.get("usage", {}).get("completion_tokens", 0)
            finish_reason = choice.get("finish_reason", "stop")

            return ProviderResponse(
                text=text,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                finish_reason=finish_reason,
                model=request.model,
                metadata={"response": data},
            )

        except Exception as e:
            logger.error(f"Generic HTTP provider invocation failed: {e}")
            raise

    def invoke_stream(
        self, request: ProviderRequest, on_chunk: Callable[[str], None]
    ) -> ProviderResponse:
        """Streaming invocation."""
        if not self._available:
            raise RuntimeError("Generic HTTP provider not available")

        try:
            payload = {
                "model": request.model,
                "messages": [{"role": "user", "content": request.prompt}],
                "temperature": request.config.temperature,
                "max_tokens": request.config.max_output_tokens,
                "stream": True,
            }

            # Stream request
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=self.headers,
                stream=True,
                timeout=180,
            )
            response.raise_for_status()

            # Parse streaming response
            full_text = ""
            for line in response.iter_lines():
                if line:
                    line_str = line.decode("utf-8")
                    if line_str.startswith("data: "):
                        data_str = line_str[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and data["choices"]:
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    chunk_text = delta["content"]
                                    full_text += chunk_text
                                    on_chunk(chunk_text)
                        except json.JSONDecodeError:
                            continue

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
            logger.error(f"Generic HTTP provider streaming failed: {e}")
            raise

    def healthcheck(self) -> bool:
        """Check if provider is available."""
        try:
            response = requests.get(
                f"{self.base_url}/health", headers=self.headers, timeout=5
            )
            return response.status_code == 200
        except Exception:
            # Try models endpoint as fallback
            try:
                response = requests.get(
                    f"{self.base_url}/v1/models",
                    headers=self.headers,
                    timeout=5,
                )
                return response.status_code == 200
            except Exception:
                return False

    def capabilities(self) -> ProviderCapabilities:
        """Returns provider capabilities."""
        return ProviderCapabilities(
            streaming=True,
            max_tokens=4096,  # Default, may vary
            rate_limits={},
            supports_seed=True,  # Assume yes for OpenAI-compatible
            supports_json_mode=False,  # Unknown
        )
