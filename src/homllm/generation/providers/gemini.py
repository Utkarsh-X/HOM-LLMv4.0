"""Google Gemini provider implementation.

Uses the new Google GenAI SDK (google.genai) which replaces the deprecated
google.generativeai package.

API Key Configuration:
    Priority order (first found wins):
    1. Explicit api_key parameter passed to __init__
    2. configs/secrets.yaml file (api_keys.gemini)
    3. GEMINI_API_KEY environment variable
"""

import logging
import os
import re
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
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None
    logger.debug("google.genai not available; GeminiProvider disabled")


def _load_api_key_from_config(provider_name: str = "gemini") -> Optional[str]:
    """
    Load API key from configs/secrets.yaml.
    
    If a gemini_pool is configured, uses the KeyRotationManager to get
    the current active key (with automatic rotation after limit).
    Otherwise falls back to the single api_keys.gemini value.
    
    Args:
        provider_name: Key name under api_keys section (e.g., 'gemini', 'openai')
    
    Returns:
        API key string if found, None otherwise
    """
    # Try pool-based rotation first (only for Gemini)
    if provider_name == "gemini":
        try:
            from homllm.common.key_rotation import KeyRotationManager
            mgr = KeyRotationManager.instance()
            if mgr._pool_mode:
                key = mgr.get_key()
                logger.debug("Loaded Gemini API key from rotation pool (slot %d)", mgr._current_index)
                return key
        except Exception as e:
            logger.debug("Key rotation pool not available, falling back to single key: %s", e)

    # Fallback: single key from secrets.yaml
    try:
        import yaml
    except ImportError:
        logger.debug("PyYAML not installed; cannot read secrets.yaml")
        return None
    
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


class GeminiProvider(ProviderConnector):
    """Google Gemini provider implementation using the new GenAI SDK."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Gemini provider.
        
        Args:
            api_key: Gemini API key. If not provided, looks for key in:
                     1. configs/secrets.yaml (api_keys.gemini)
                     2. GEMINI_API_KEY environment variable
        """
        self._client: Optional[object] = None
        self._available = False
        self._active_pool_key: Optional[str] = None  # Track current pool key

        if genai is not None:
            try:
                # Priority: explicit param > config file (pool or single) > env var
                resolved_key = api_key
                
                if not resolved_key:
                    # Try loading from config file (pool-aware)
                    resolved_key = _load_api_key_from_config("gemini")
                    if resolved_key:
                        logger.info("Using Gemini API key from configs/secrets.yaml")
                
                # Create client (will fall back to GEMINI_API_KEY env var if no key provided)
                if resolved_key:
                    self._client = genai.Client(api_key=resolved_key)
                    self._active_pool_key = resolved_key
                else:
                    # Let SDK try environment variable
                    self._client = genai.Client()
                
                self._available = True
                logger.info("Gemini provider initialized (new GenAI SDK)")
            except Exception as e:
                logger.debug(f"Gemini provider unavailable: {e}")

    def invoke_sync(self, request: ProviderRequest) -> ProviderResponse:
        """Synchronous invocation."""
        if not self._available or self._client is None:
            raise RuntimeError("Gemini provider not available")

        # --- Key rotation: re-check active key before each call ---
        self._maybe_rotate_key()

        try:
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

            # Invoke API with bounded retries for transient provider failures.
            start_time = time.time()
            response = self._invoke_with_retry(
                model=request.model,
                prompt=request.prompt,
                config_dict=config_dict,
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

            # --- Key rotation: record successful usage ---
            self._record_key_usage()

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

    def _maybe_rotate_key(self) -> None:
        """Check if the current key is exhausted and re-init client with next key."""
        try:
            from homllm.common.key_rotation import KeyRotationManager
            mgr = KeyRotationManager.instance()
            if not mgr._pool_mode:
                return
            new_key = mgr.get_key()
            # If the key changed, re-initialize the Gemini client
            if new_key != self._active_pool_key:
                logger.info(
                    "[KEY_ROTATION] Switching Gemini client to new key (slot %d)",
                    mgr._current_index,
                )
                self._active_pool_key = new_key
                self._client = genai.Client(api_key=new_key)
        except Exception as e:
            logger.debug("Key rotation check skipped: %s", e)

    def _record_key_usage(self) -> None:
        """Record a successful API call against the current key."""
        try:
            from homllm.common.key_rotation import KeyRotationManager
            mgr = KeyRotationManager.instance()
            if mgr._pool_mode:
                mgr.record_usage()
        except Exception as e:
            logger.debug("Key rotation usage recording skipped: %s", e)

    def _invoke_with_retry(self, model: str, prompt: str, config_dict: dict):
        max_attempts = 4
        for attempt in range(1, max_attempts + 1):
            try:
                return self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config_dict,
                )
            except Exception as e:
                if attempt >= max_attempts or not self._is_retryable_exception(e):
                    raise
                sleep_s = self._retry_delay_seconds(e, attempt)
                logger.warning(
                    "[GEMINI_RETRY] transient error attempt=%d/%d sleep=%.1fs err=%s",
                    attempt,
                    max_attempts,
                    sleep_s,
                    str(e),
                )
                time.sleep(sleep_s)
        raise RuntimeError("Gemini retry loop exhausted unexpectedly")

    @staticmethod
    def _is_retryable_exception(exc: Exception) -> bool:
        msg = str(exc).lower()
        retry_tokens = (
            "429",
            "rate limit",
            "resource exhausted",
            "quota",
            "temporarily unavailable",
            "unavailable",
            "deadline exceeded",
            "timeout",
            "timed out",
            "internal error",
            "500",
            "503",
            "connection reset",
        )
        return any(tok in msg for tok in retry_tokens)

    @staticmethod
    def _retry_delay_seconds(exc: Exception, attempt: int) -> float:
        """
        Prefer provider-suggested retry delay when available.
        Fallback: attempts 1-3 use short linear backoff (1.5s, 3s, 4.5s).
        Attempt 4 uses a longer 5s cooldown for better recovery.
        """
        msg = str(exc)
        lower = msg.lower()
        # Gemini errors often contain: "Please retry in 39.88s."
        m = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", lower)
        if m:
            try:
                suggested = float(m.group(1))
                return max(1.0, min(60.0, suggested + 0.5))
            except Exception:
                pass
        # Attempt 4 gets a longer gap (5s) for better recovery
        if attempt >= 4:
            return 5.0
        return min(15.0, 1.5 * attempt)

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
            max_tokens=1040000,  # Gemini 1.5/2.5 Flash context limit with safety buffer
            rate_limits={"requests_per_minute": 60, "tokens_per_minute": 1000000},
            supports_seed=True,  # New SDK supports seed
            supports_json_mode=True,  # New SDK supports JSON mode
        )
