"""Local provider implementation (ollama/vLLM)."""

import logging
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
    import ollama
except ImportError:
    ollama = None
    logger.warning("ollama not available, LocalProvider disabled")


class LocalProvider(ProviderConnector):
    """Local provider using ollama or vLLM."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        """
        Initialize local provider.
        
        Args:
            base_url: Ollama base URL (default: localhost)
            model: Model name to use
        """
        self.base_url = base_url
        self.default_model = model
        self._available = False

        if ollama is not None:
            try:
                # Test connection
                self._available = self.healthcheck()
            except Exception as e:
                logger.warning(f"Local provider unavailable: {e}")

    def invoke_sync(self, request: ProviderRequest) -> ProviderResponse:
        """Synchronous invocation."""
        if not self._available or ollama is None:
            raise RuntimeError("Local provider not available")

        try:
            start_time = time.time()

            # Prepare ollama request
            model = request.model or self.default_model
            options = {
                "temperature": request.config.temperature,
                "num_predict": request.config.max_output_tokens,
            }

            if request.config.seed is not None:
                options["seed"] = request.config.seed

            # Invoke ollama
            response = ollama.generate(
                model=model,
                prompt=request.prompt,
                options=options,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract response
            text = response.get("response", "")
            tokens_in = len(request.prompt.split())  # Rough estimate
            tokens_out = response.get("eval_count", 0)

            return ProviderResponse(
                text=text,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                finish_reason="stop",
                model=model,
                metadata={"response": response},
            )

        except Exception as e:
            logger.error(f"Local provider invocation failed: {e}")
            raise

    def invoke_stream(
        self, request: ProviderRequest, on_chunk: Callable[[str], None]
    ) -> ProviderResponse:
        """Streaming invocation."""
        if not self._available or ollama is None:
            raise RuntimeError("Local provider not available")

        try:
            model = request.model or self.default_model
            options = {
                "temperature": request.config.temperature,
                "num_predict": request.config.max_output_tokens,
            }

            if request.config.seed is not None:
                options["seed"] = request.config.seed

            # Stream response
            full_text = ""
            for chunk in ollama.generate(
                model=model,
                prompt=request.prompt,
                options=options,
                stream=True,
            ):
                chunk_text = chunk.get("response", "")
                full_text += chunk_text
                on_chunk(chunk_text)

            tokens_in = len(request.prompt.split())
            tokens_out = len(full_text.split())

            return ProviderResponse(
                text=full_text,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                finish_reason="stop",
                model=model,
                metadata={},
            )

        except Exception as e:
            logger.error(f"Local provider streaming failed: {e}")
            raise

    def healthcheck(self) -> bool:
        """Check if provider is available."""
        if ollama is None:
            return False

        try:
            # Try to list models
            ollama.list()
            return True
        except Exception:
            return False

    def capabilities(self) -> ProviderCapabilities:
        """Returns provider capabilities."""
        return ProviderCapabilities(
            streaming=True,
            max_tokens=8192,  # Typical for local models
            rate_limits={},
            supports_seed=True,
            supports_json_mode=False,
        )
