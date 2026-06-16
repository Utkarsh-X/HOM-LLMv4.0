"""Shared retry policy for provider calls."""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

T = TypeVar("T")

# Initial attempt happens immediately (0s), then 6 retries.
LLM_RETRY_DELAYS_SECONDS: list[int] = [0, 5, 10, 15, 20, 20, 20]


def is_retryable_llm_exception(exc: Exception) -> bool:
    """Return True when an exception looks transient/retryable."""
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
        "502",
        "503",
        "504",
        "connection reset",
        "connection error",
        "server error",
        "service unavailable",
        "getaddrinfo failed",
        "name resolution",
        "temporary failure in name resolution",
        "failed to establish a new connection",
        "connection aborted",
        "connection refused",
        "network is unreachable",
    )
    return any(tok in msg for tok in retry_tokens)


def call_with_llm_retries(
    fn: Callable[[], T],
    *,
    logger: logging.Logger,
    label: str,
    on_exception: Callable[[Exception], None] | None = None,
    is_retryable: Callable[[Exception], bool] = is_retryable_llm_exception,
) -> T:
    """
    Call `fn` with fixed aggressive retries.

    Schedule uses `LLM_RETRY_DELAYS_SECONDS` as delay BEFORE each attempt.
    """
    last_exc: Exception | None = None
    total_attempts = len(LLM_RETRY_DELAYS_SECONDS)

    for attempt, delay in enumerate(LLM_RETRY_DELAYS_SECONDS, start=1):
        if delay > 0:
            time.sleep(delay)
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if on_exception is not None:
                try:
                    on_exception(exc)
                except Exception:
                    # Retry path should not crash on hook exceptions.
                    pass

            if attempt >= total_attempts or not is_retryable(exc):
                raise

            next_delay = LLM_RETRY_DELAYS_SECONDS[attempt]
            logger.warning(
                "[%s_RETRY] Attempt %d/%d failed (next retry in %ss): %s",
                label,
                attempt,
                total_attempts,
                next_delay,
                str(exc),
            )

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{label} retry loop ended without result")
