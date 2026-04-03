"""LLM-based judge for HOM-LLM delta evaluation.

Compares HOM-LLM answers to the fixed Cursor baseline and emits
per-dimension ordinal scores plus natural-language explanations.

Constraints:
- Uses separate judge config (model + API key).
- No imports from homllm core.
- Read-only baseline (no regeneration).
- Deterministic output writes (overwrite by default, explicit append optional).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

# ------------------------------- METRIC NAMES -------------------------------
METRIC_DISPLAY_NAMES = {
    "semantic_correctness": "Semantic Correctness",
    "factual_consistency": "Factual Consistency",
    "completeness": "Completeness",
    "clarity": "Clarity",
    "relevance": "Relevance",
    "hallucination_risk": "Hallucination Safety",
    "verbosity": "Verbosity (lower=better)",
    "overall_quality": "Overall Quality",
}

METRIC_ORDER = [
    "semantic_correctness",
    "factual_consistency",
    "completeness",
    "clarity",
    "relevance",
    "hallucination_risk",
    "verbosity",
    "overall_quality",
]

SUPPORTED_PROVIDERS = {"openai", "gemini", "cerebras_sdk", "cerebras"}


def configure_console_encoding() -> None:
    """Prefer UTF-8 console output on Windows to avoid print crashes."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def normalize_provider_name(name: Optional[str]) -> str:
    value = (name or "").strip().lower()
    if value == "cerebras":
        return "cerebras_sdk"
    return value or "openai"


def safe_filename_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    token = token.strip("._-")
    return token or "unknown"


# ------------------------------- IO HELPERS -------------------------------
def read_json(path: Path) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_yaml(path: Path) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML object at root of {path}")
    return payload


def read_jsonl(path: Path) -> List[Dict]:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: List[Dict], mode: str = "w") -> None:
    with open(path, mode, encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def dedupe_records_by_query_id(records: List[Dict]) -> List[Dict]:
    """
    Keep one record per query_id.

    If duplicates exist, latest record wins while preserving first-seen order.
    """
    order: List[Any] = []
    by_qid: Dict[Any, Dict] = {}
    for rec in records:
        qid = rec.get("query_id")
        if qid not in by_qid:
            order.append(qid)
        by_qid[qid] = rec
    return [by_qid[qid] for qid in order]


# ------------------------------- RATE LIMITER -------------------------------
class RateLimiter:
    """
    Token bucket rate limiter for controlling LLM API request rate.
    
    Thread-safe implementation with configurable requests per minute.
    
    Usage:
        limiter = RateLimiter(requests_per_minute=10)
        limiter.acquire()  # Blocks until a request slot is available
    """
    
    def __init__(self, requests_per_minute: int = 60, safety_seconds: float = 0.25):
        """
        Initialize rate limiter.
        
        Args:
            requests_per_minute: Maximum requests allowed per minute.
                                 Default is 60 (1 per second).
                                 Set to 0 or negative to disable limiting.
        """
        self.rpm = requests_per_minute
        self.enabled = requests_per_minute > 0
        self.window_seconds = 60.0
        self.safety_seconds = max(0.0, float(safety_seconds))
        self.min_interval_seconds = (self.window_seconds / requests_per_minute) if self.enabled else 0.0
        self._lock = threading.Lock()
        self._request_count = 0
        self._request_times = deque()
        self._last_request_time = None
    
    def acquire(self) -> float:
        """
        Acquire a request slot, blocking if necessary.
        
        Returns:
            Wait time in seconds (0 if no wait was needed)
        """
        if not self.enabled:
            return 0.0
        
        with self._lock:
            total_wait = 0.0

            # Strict limiter: enforce both
            # 1) rolling-window cap and
            # 2) minimum inter-request spacing.
            while True:
                now = time.monotonic()
                cutoff = now - self.window_seconds
                while self._request_times and self._request_times[0] <= cutoff:
                    self._request_times.popleft()

                wait_window = 0.0
                if len(self._request_times) >= self.rpm:
                    oldest = self._request_times[0]
                    wait_window = (oldest + self.window_seconds + self.safety_seconds) - now

                wait_interval = 0.0
                if self._last_request_time is not None:
                    wait_interval = (
                        (self._last_request_time + self.min_interval_seconds + self.safety_seconds)
                        - now
                    )

                wait_time = max(wait_window, wait_interval, 0.0)
                wait_time = max(0.0, wait_time)
                if wait_time <= 0:
                    now = time.monotonic()
                    self._request_times.append(now)
                    self._last_request_time = now
                    self._request_count += 1
                    return total_wait

                time.sleep(wait_time)
                total_wait += wait_time
    
    @property
    def request_count(self) -> int:
        """Total requests made through this limiter."""
        return self._request_count
    
    def __repr__(self) -> str:
        status = f"{self.rpm} RPM" if self.enabled else "disabled"
        return f"RateLimiter({status}, requests={self._request_count})"


# ------------------------------- CONFIG -------------------------------
@dataclass
class GeminiKeyPoolConfig:
    secrets_file: Path
    pool_name: str
    state_file: Path
    requests_per_key: int
    daily_reset_hour: Optional[int]
    keys: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class JudgeConfig:
    model: str
    api_key: Optional[str]
    provider: str = "openai"  # "openai" | "gemini" | "cerebras_sdk"
    base_url: Optional[str] = None
    requests_per_minute: int = 60  # Default: 60 RPM (1 per second)
    temperature: float = 0.0
    top_p: Optional[float] = None
    max_completion_tokens: Optional[int] = None
    stream: bool = False
    reasoning_effort: Optional[str] = None
    # Optional raw request-body fields forwarded to the OpenAI-compatible API.
    # Example:
    #   "extra_body": {"disable_reasoning": false, "clear_thinking": false}
    extra_body: Optional[Dict[str, Any]] = None
    api_key_pool: Optional[GeminiKeyPoolConfig] = None


class GeminiKeyPoolManager:
    """Persistent sequential Gemini key rotation with per-key request quotas."""

    def __init__(self, cfg: GeminiKeyPoolConfig):
        self.cfg = cfg
        self.cfg.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load_state()
        self._maybe_reset()
        self._ensure_available_key()

    def _current_reset_marker(self) -> Optional[str]:
        if self.cfg.daily_reset_hour is None:
            return None
        now_local = datetime.now().astimezone()
        marker_date = now_local.date()
        if now_local.hour < int(self.cfg.daily_reset_hour):
            marker_date = marker_date.fromordinal(marker_date.toordinal() - 1)
        return marker_date.isoformat()

    def _default_state(self) -> Dict[str, Any]:
        return {
            "current_index": 0,
            "used_counts": [0 for _ in self.cfg.keys],
            "reset_marker": self._current_reset_marker(),
        }

    def _load_state(self) -> Dict[str, Any]:
        if not self.cfg.state_file.exists():
            return self._default_state()
        try:
            payload = json.loads(self.cfg.state_file.read_text(encoding="utf-8"))
        except Exception:
            return self._default_state()
        if not isinstance(payload, dict):
            return self._default_state()
        counts = payload.get("used_counts")
        if not isinstance(counts, list):
            counts = []
        counts = [int(v) if isinstance(v, (int, float)) else 0 for v in counts]
        if len(counts) < len(self.cfg.keys):
            counts.extend([0] * (len(self.cfg.keys) - len(counts)))
        elif len(counts) > len(self.cfg.keys):
            counts = counts[: len(self.cfg.keys)]
        current_index = payload.get("current_index", 0)
        if not isinstance(current_index, int):
            current_index = 0
        current_index = max(0, min(current_index, max(len(self.cfg.keys) - 1, 0)))
        return {
            "current_index": current_index,
            "used_counts": counts,
            "reset_marker": payload.get("reset_marker"),
        }

    def _save_state(self) -> None:
        self.cfg.state_file.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def _maybe_reset(self) -> None:
        marker = self._current_reset_marker()
        if marker is None:
            return
        if self.state.get("reset_marker") == marker:
            return
        self.state = self._default_state()
        self._save_state()

    def _advance_to_available(self) -> None:
        total = len(self.cfg.keys)
        for offset in range(1, total + 1):
            idx = (self.state["current_index"] + offset) % total
            if self.state["used_counts"][idx] < self.cfg.requests_per_key:
                self.state["current_index"] = idx
                self._save_state()
                return
        raise RuntimeError("All Gemini pool keys are exhausted for the current reset window.")

    def _ensure_available_key(self) -> None:
        if self.state["used_counts"][self.state["current_index"]] >= self.cfg.requests_per_key:
            self._advance_to_available()

    def current_key(self) -> str:
        self._maybe_reset()
        self._ensure_available_key()
        return str(self.cfg.keys[self.state["current_index"]]["key"])

    def current_name(self) -> str:
        self._maybe_reset()
        self._ensure_available_key()
        return str(self.cfg.keys[self.state["current_index"]]["name"])

    def mark_success(self) -> None:
        self._maybe_reset()
        idx = self.state["current_index"]
        self.state["used_counts"][idx] += 1
        if self.state["used_counts"][idx] >= self.cfg.requests_per_key:
            self._save_state()
            self._advance_to_available()
        else:
            self._save_state()

    def mark_quota_exhausted(self) -> None:
        self._maybe_reset()
        idx = self.state["current_index"]
        self.state["used_counts"][idx] = self.cfg.requests_per_key
        self._save_state()
        self._advance_to_available()


def _load_gemini_key_pool(pool_cfg: Dict[str, Any], config_dir: Path) -> GeminiKeyPoolConfig:
    if not isinstance(pool_cfg, dict):
        raise ValueError("judge_config api_key_pool must be an object.")

    secrets_path = pool_cfg.get("secrets_file", "configs/secrets.yaml")
    secrets_path = Path(secrets_path)
    if not secrets_path.is_absolute():
        secrets_path = (config_dir.parent / secrets_path).resolve()

    secrets = read_yaml(secrets_path)
    api_keys = secrets.get("api_keys", {})
    if not isinstance(api_keys, dict):
        raise ValueError(f"Missing api_keys mapping in {secrets_path}")

    pool_name = str(pool_cfg.get("pool_name", "gemini_pool"))
    raw_pool = api_keys.get(pool_name)
    if not isinstance(raw_pool, dict):
        raise ValueError(f"Missing api_keys.{pool_name} in {secrets_path}")

    raw_keys = raw_pool.get("keys", [])
    if not isinstance(raw_keys, list) or not raw_keys:
        raise ValueError(f"api_keys.{pool_name}.keys must be a non-empty list")

    keys: List[Dict[str, str]] = []
    for idx, item in enumerate(raw_keys, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid key entry at index {idx} in api_keys.{pool_name}.keys")
        name = str(item.get("name") or f"{pool_name}_{idx}")
        key = str(item.get("key") or "").strip()
        if not key:
            raise ValueError(f"Missing key value for api_keys.{pool_name}.keys[{idx}]")
        keys.append({"name": name, "key": key})

    state_path = pool_cfg.get("state_file", "logs/judge_gemini_pool_state.json")
    state_path = Path(state_path)
    if not state_path.is_absolute():
        state_path = (config_dir.parent / state_path).resolve()

    requests_per_key = pool_cfg.get("requests_per_key", raw_pool.get("requests_per_key", 20))
    if not isinstance(requests_per_key, int) or requests_per_key <= 0:
        raise ValueError("requests_per_key must be a positive integer")

    daily_reset_hour = pool_cfg.get("daily_reset_hour", raw_pool.get("daily_reset_hour"))
    if daily_reset_hour is not None:
        if not isinstance(daily_reset_hour, int) or daily_reset_hour < 0 or daily_reset_hour > 23:
            raise ValueError("daily_reset_hour must be null or an integer in [0, 23]")

    return GeminiKeyPoolConfig(
        secrets_file=secrets_path,
        pool_name=pool_name,
        state_file=state_path,
        requests_per_key=requests_per_key,
        daily_reset_hour=daily_reset_hour,
        keys=keys,
    )


def _select_provider_cfg(raw_cfg: Dict[str, Any], provider_override: Optional[str]) -> Dict[str, Any]:
    # New schema:
    # {
    #   "default_provider": "openai",
    #   "providers": {"openai": {...}, "gemini": {...}, "cerebras_sdk": {...}}
    # }
    provider_blocks = raw_cfg.get("providers")
    if isinstance(provider_blocks, dict):
        chosen = normalize_provider_name(provider_override or raw_cfg.get("default_provider", "openai"))
        if chosen not in SUPPORTED_PROVIDERS:
            allowed = ", ".join(sorted(SUPPORTED_PROVIDERS))
            raise ValueError(f"judge_config provider must be one of: {allowed}")

        # Accept alias key "cerebras" in provider blocks.
        section = provider_blocks.get(chosen)
        if section is None and chosen == "cerebras_sdk":
            section = provider_blocks.get("cerebras")
        if section is None:
            available = ", ".join(sorted(provider_blocks.keys()))
            raise ValueError(
                f"judge_config missing providers.{chosen} section. Available sections: {available}"
            )
        if not isinstance(section, dict):
            raise ValueError(f"judge_config providers.{chosen} must be an object.")

        merged = dict(section)
        merged["provider"] = chosen
        return merged

    # Legacy flat schema fallback.
    merged = dict(raw_cfg)
    if provider_override:
        merged["provider"] = provider_override
    return merged


def load_judge_config(path: Path, provider_override: Optional[str] = None) -> JudgeConfig:
    raw_cfg = read_json(path)
    cfg = _select_provider_cfg(raw_cfg, provider_override)

    model = cfg.get("model")
    api_key = cfg.get("api_key")
    provider = normalize_provider_name(cfg.get("provider", "openai"))
    if provider not in SUPPORTED_PROVIDERS:
        allowed = ", ".join(sorted(SUPPORTED_PROVIDERS))
        raise ValueError(f"judge_config field 'provider' must be one of: {allowed}")
    provider = normalize_provider_name(provider)
    base_url = cfg.get("base_url")
    requests_per_minute = cfg.get("requests_per_minute", 60)
    temperature = cfg.get("temperature", 0.0)
    top_p = cfg.get("top_p")
    max_completion_tokens = cfg.get("max_completion_tokens")
    stream = cfg.get("stream", False)
    reasoning_effort = cfg.get("reasoning_effort")
    extra_body = cfg.get("extra_body")
    api_key_pool_cfg = cfg.get("api_key_pool")
    if extra_body is not None and not isinstance(extra_body, dict):
        raise ValueError("judge_config.json field 'extra_body' must be an object if provided.")
    if temperature is None:
        temperature = 0.0
    if not isinstance(temperature, (int, float)):
        raise ValueError("judge_config.json field 'temperature' must be numeric if provided.")
    if top_p is not None and not isinstance(top_p, (int, float)):
        raise ValueError("judge_config.json field 'top_p' must be numeric if provided.")
    if max_completion_tokens is not None and not isinstance(max_completion_tokens, int):
        raise ValueError("judge_config.json field 'max_completion_tokens' must be an integer if provided.")
    if not isinstance(stream, bool):
        raise ValueError("judge_config.json field 'stream' must be boolean if provided.")
    if reasoning_effort is not None and not isinstance(reasoning_effort, str):
        raise ValueError("judge_config.json field 'reasoning_effort' must be a string if provided.")
    gemini_pool = None
    if provider == "gemini" and isinstance(api_key_pool_cfg, dict) and not api_key:
        # Only load the key pool when no direct api_key is provided.
        # To skip the pool, add "api_key": "<your-key>" to the provider block.
        gemini_pool = _load_gemini_key_pool(api_key_pool_cfg, path.parent.resolve())
        api_key = gemini_pool.keys[0]["key"]

    if not model or not api_key:
        raise ValueError(
            f"judge_config provider section '{provider}' must include 'model' and 'api_key', "
            "or provide a valid api_key_pool for Gemini."
        )
    return JudgeConfig(
        model=model, 
        api_key=api_key, 
        provider=provider, 
        base_url=base_url,
        requests_per_minute=requests_per_minute,
        temperature=float(temperature),
        top_p=float(top_p) if top_p is not None else None,
        max_completion_tokens=max_completion_tokens,
        stream=stream,
        reasoning_effort=reasoning_effort,
        extra_body=extra_body,
        api_key_pool=gemini_pool,
    )


# ------------------------------- PROMPT -------------------------------
def build_prompt(baseline_answer: str, candidate_answer: str, query_text: str) -> List[Dict[str, str]]:
    system_msg = (
        "You are an impartial evaluator comparing two answers to the same query.\n"
        "Focus on relative quality. Output ONLY valid JSON.\n\n"
        "CRITICAL: For each metric, you MUST output PAIRED scores comparing BOTH answers.\n"
        "Scores are integers 1-5 (1=poor, 5=excellent).\n"
        "For verbosity: lower is better (1=concise, 5=verbose).\n"
        "For hallucination_risk: higher is SAFER (1=very risky, 5=very safe).\n\n"
        "Required JSON format:\n"
        "{\n"
        '  "scores": {\n'
        '    "semantic_correctness": {"baseline": X, "candidate": Y},\n'
        '    "factual_consistency": {"baseline": X, "candidate": Y},\n'
        '    "completeness": {"baseline": X, "candidate": Y},\n'
        '    "clarity": {"baseline": X, "candidate": Y},\n'
        '    "relevance": {"baseline": X, "candidate": Y},\n'
        '    "hallucination_risk": {"baseline": X, "candidate": Y},\n'
        '    "verbosity": {"baseline": X, "candidate": Y},\n'
        '    "overall_quality": {"baseline": X, "candidate": Y}\n'
        "  },\n"
        '  "verdict": "improved|equal|regressed",\n'
        '  "explanation": "1-3 sentence rationale",\n'
        '  "key_differences": ["bullet 1", "bullet 2", ...]\n'
        "}"
    )
    user_msg = (
        f"Query:\n{query_text}\n\n"
        "=== BASELINE ANSWER (Cursor) ===\n"
        f"{baseline_answer}\n\n"
        "=== CANDIDATE ANSWER (HOM-LLM) ===\n"
        f"{candidate_answer}\n\n"
        "Evaluate and return the JSON with paired scores for all 8 metrics."
    )
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


# ------------------------------- API CLIENTS -------------------------------
def ensure_openai_client(cfg: JudgeConfig):
    try:
        from openai import OpenAI
    except Exception as exc:
        raise RuntimeError(
            "openai package is required for the judge. Install via `pip install openai`."
        ) from exc

    client_kwargs: Dict[str, Any] = {"api_key": cfg.api_key}
    if cfg.base_url:
        client_kwargs["base_url"] = cfg.base_url
    return OpenAI(**client_kwargs)


def ensure_gemini_client(cfg: JudgeConfig):
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "google-genai package is required for Gemini judge. Install via `pip install google-genai`."
        ) from exc
    return genai.Client(api_key=cfg.api_key)


def ensure_cerebras_client(cfg: JudgeConfig):
    try:
        from cerebras.cloud.sdk import Cerebras
    except Exception as exc:
        raise RuntimeError(
            "cerebras-cloud-sdk package is required for cerebras_sdk judge provider. "
            "Install via `pip install cerebras-cloud-sdk`."
        ) from exc

    client_kwargs: Dict[str, Any] = {"api_key": cfg.api_key}
    if cfg.base_url:
        client_kwargs["base_url"] = cfg.base_url
    try:
        return Cerebras(**client_kwargs)
    except TypeError:
        # Some SDK versions may not expose base_url; retry with required args only.
        if "base_url" in client_kwargs:
            sys.stderr.write(
                "[WARN] Cerebras SDK constructor does not accept base_url; retrying without it.\n"
            )
            client_kwargs.pop("base_url", None)
            return Cerebras(**client_kwargs)
        raise


# ------------------------------- RETRY WRAPPER -------------------------------
# Delays: 1st try (0s), 2nd try (1s), 3rd try (1s), 4th try (3s), 5th try (5s)
_JUDGE_RETRY_DELAYS = [0, 5, 5, 10, 10, 5, 10, 20]  # delay BEFORE each attempt


def _is_retryable_judge_error(exc: Exception) -> bool:
    """Check if an exception is a transient error worth retrying."""
    msg = str(exc).lower()
    retry_tokens = (
        "429", "rate limit", "resource exhausted", "quota",
        "temporarily unavailable", "unavailable",
        "deadline exceeded", "timeout", "timed out",
        "internal error", "500", "503",
        "connection reset", "connection error",
        "server error", "service unavailable",
        "empty content",
    )
    return any(tok in msg for tok in retry_tokens)


def _is_quota_exhausted_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    quota_tokens = (
        "quota exceeded",
        "resource exhausted",
        "generaterequestsperdayperprojectpermodel",
        "free tier",
        "perday",
    )
    return any(tok in msg for tok in quota_tokens)


def _retry_judge_call(fn, *args, **kwargs):
    """
    Retry a judge API call up to 5 times with escalating delays.

    Schedule: try1(0s) -> try2(1s) -> try3(1s) -> try4(3s) -> try5(5s)
    Only retries transient errors. Auth/config errors propagate immediately.
    """
    last_exc = None
    for attempt, delay in enumerate(_JUDGE_RETRY_DELAYS, 1):
        if delay > 0:
            time.sleep(delay)
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if _is_quota_exhausted_error(exc):
                raise
            if not _is_retryable_judge_error(exc) or attempt >= len(_JUDGE_RETRY_DELAYS):
                raise
            sys.stderr.write(
                f"[JUDGE_RETRY] Attempt {attempt}/{len(_JUDGE_RETRY_DELAYS)} failed "
                f"(next retry in {_JUDGE_RETRY_DELAYS[attempt]}s): {exc}\n"
            )
    raise last_exc  # Should never reach here


def _extract_balanced_json_object(text: str) -> Optional[str]:
    """Extract the first balanced JSON object from free-form text."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _strip_code_fences(text: str) -> str:
    """Remove common markdown wrappers around JSON output."""
    stripped = text.strip()
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _repair_json_commas(text: str) -> str:
    """Repair a common invalid JSON pattern: trailing commas."""
    return re.sub(r",\s*([}\]])", r"\1", text)


def _parse_judge_json(content: str) -> Dict:
    """
    Parse judge JSON robustly from model output.

    Attempts:
    1) raw parse
    2) parse fenced-stripped text
    3) parse balanced JSON object
    4) parse repaired trailing-comma JSON
    """
    candidates: List[str] = []
    raw = content.strip()
    if raw:
        candidates.append(raw)
    stripped = _strip_code_fences(raw)
    if stripped and stripped not in candidates:
        candidates.append(stripped)
    balanced = _extract_balanced_json_object(stripped)
    if balanced and balanced not in candidates:
        candidates.append(balanced)
    if balanced:
        repaired = _repair_json_commas(balanced)
        if repaired and repaired not in candidates:
            candidates.append(repaired)

    last_error: Optional[Exception] = None
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc

    raise RuntimeError(
        f"Failed to parse judge JSON after recovery attempts. Raw prefix: {raw[:200]!r}"
    ) from last_error


def _call_openai_api(client, cfg: JudgeConfig, kwargs: Dict[str, Any]):
    """Raw OpenAI API call (wrapped by retry logic)."""
    try:
        return client.chat.completions.create(**kwargs)
    except TypeError as exc:
        if "extra_body" in kwargs:
            sys.stderr.write(
                "[WARN] OpenAI client does not accept extra_body; retrying without it.\n"
            )
            kwargs.pop("extra_body", None)
            return client.chat.completions.create(**kwargs)
        raise


def call_judge_openai(client, cfg: JudgeConfig, messages: List[Dict[str, str]]) -> Tuple[Dict, str]:
    kwargs: Dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "temperature": float(cfg.temperature),
        "max_tokens": 1500,
        "response_format": {"type": "json_object"},
    }
    if cfg.extra_body:
        kwargs["extra_body"] = cfg.extra_body

    completion = _retry_judge_call(_call_openai_api, client, cfg, kwargs)
    content = completion.choices[0].message.content
    if not content:
        raise RuntimeError("Judge model returned empty content.")
    used_model = getattr(completion, "model", None) or cfg.model
    return _parse_judge_json(content), str(used_model)


def _call_gemini_api(client, cfg: JudgeConfig, prompt: str):
    """Raw Gemini API call (wrapped by retry logic)."""
    
    paired_score_schema = {
        "type": "object",
        "properties": {
            "baseline": {
                "type": "integer", 
                "description": "Score for the baseline answer, 1-5 (1=poor, 5=excellent)."
            },
            "candidate": {
                "type": "integer", 
                "description": "Score for the candidate answer, 1-5 (1=poor, 5=excellent)."
            }
        },
        "required": ["baseline", "candidate"]
    }
    
    verbosity_score_schema = {
        "type": "object",
        "properties": {
            "baseline": {
                "type": "integer", 
                "description": "Verbosity score for baseline answer, 1-5 (lower is better: 1=concise, 5=verbose)."
            },
            "candidate": {
                "type": "integer", 
                "description": "Verbosity score for candidate answer, 1-5 (lower is better: 1=concise, 5=verbose)."
            }
        },
        "required": ["baseline", "candidate"]
    }
    
    hallucination_score_schema = {
        "type": "object",
        "properties": {
            "baseline": {
                "type": "integer", 
                "description": "Safety score for baseline answer, 1-5 (higher is SAFER: 1=very risky, 5=very safe)."
            },
            "candidate": {
                "type": "integer", 
                "description": "Safety score for candidate answer, 1-5 (higher is SAFER: 1=very risky, 5=very safe)."
            }
        },
        "required": ["baseline", "candidate"]
    }

    judge_schema = {
        "type": "object",
        "properties": {
            "scores": {
                "type": "object",
                "properties": {
                    "semantic_correctness": paired_score_schema,
                    "factual_consistency": paired_score_schema,
                    "completeness": paired_score_schema,
                    "clarity": paired_score_schema,
                    "relevance": paired_score_schema,
                    "hallucination_risk": hallucination_score_schema,
                    "verbosity": verbosity_score_schema,
                    "overall_quality": paired_score_schema
                },
                "required": [
                    "semantic_correctness", "factual_consistency", "completeness", 
                    "clarity", "relevance", "hallucination_risk", "verbosity", 
                    "overall_quality"
                ]
            },
            "verdict": {
                "type": "string", 
                "enum": ["improved", "equal", "regressed"],
                "description": "Final verdict comparing candidate to baseline."
            },
            "explanation": {
                "type": "string",
                "description": "1-3 sentence rationale"
            },
            "key_differences": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Bullet points highlighting specific differences"
            }
        },
        "required": ["scores", "verdict", "explanation", "key_differences"]
    }

    response = client.models.generate_content(
        model=cfg.model,
        contents=prompt,
        config={
            "temperature": float(cfg.temperature),
            "max_output_tokens": 4000,
            "response_mime_type": "application/json",
            "response_json_schema": judge_schema,
        },
    )
    content = response.text if response.text else ""
    if not content:
        raise RuntimeError("Gemini judge returned empty content.")
    return response, content


def call_judge_gemini(client, cfg: JudgeConfig, messages: List[Dict[str, str]]) -> Tuple[Dict, str]:
    system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
    prompt = f"{system_msg}\n\n{user_msg}" if system_msg else user_msg

    response, content = _retry_judge_call(_call_gemini_api, client, cfg, prompt)
    used_model = (
        getattr(response, "model", None)
        or getattr(response, "model_version", None)
        or cfg.model
    )

    try:
        return _parse_judge_json(content), str(used_model)
    except Exception:
        # One strict retry with explicit format constraints.
        retry_prompt = (
            f"{prompt}\n\n"
            "IMPORTANT: Return exactly one valid JSON object only. "
            "No markdown, no code fences, no comments, no trailing commas."
        )
        retry_resp, retry_text = _retry_judge_call(_call_gemini_api, client, cfg, retry_prompt)
        retry_used_model = (
            getattr(retry_resp, "model", None)
            or getattr(retry_resp, "model_version", None)
            or cfg.model
        )
        return _parse_judge_json(retry_text), str(retry_used_model)


def _call_cerebras_api(client, cfg: JudgeConfig, kwargs: Dict[str, Any]):
    """Raw Cerebras API call (wrapped by retry logic)."""
    content: Optional[str] = None
    used_model: Optional[str] = None
    if cfg.stream:
        kwargs["stream"] = True
        stream = client.chat.completions.create(**kwargs)
        chunks: List[str] = []
        for chunk in stream:
            if not used_model:
                used_model = getattr(chunk, "model", None)
            try:
                delta = chunk.choices[0].delta.content
                if delta:
                    chunks.append(delta)
            except Exception:
                continue
        content = "".join(chunks).strip()
    else:
        kwargs["stream"] = False
        completion = client.chat.completions.create(**kwargs)
        used_model = getattr(completion, "model", None)
        content = completion.choices[0].message.content if completion.choices else None

    if not content:
        raise RuntimeError("Cerebras judge returned empty content.")
    return content, used_model


def call_judge_cerebras(client, cfg: JudgeConfig, messages: List[Dict[str, str]]) -> Tuple[Dict, str]:
    kwargs: Dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "temperature": float(cfg.temperature),
    }
    if cfg.top_p is not None:
        kwargs["top_p"] = float(cfg.top_p)
    if cfg.max_completion_tokens is not None:
        kwargs["max_completion_tokens"] = int(cfg.max_completion_tokens)
    if cfg.reasoning_effort:
        kwargs["reasoning_effort"] = cfg.reasoning_effort

    content, used_model = _retry_judge_call(_call_cerebras_api, client, cfg, kwargs)
    return _parse_judge_json(content), str(used_model or cfg.model)


def call_judge(client, cfg: JudgeConfig, messages: List[Dict[str, str]]) -> Tuple[Dict, str]:
    provider = normalize_provider_name(cfg.provider)
    if provider == "gemini":
        return call_judge_gemini(client, cfg, messages)
    if provider == "cerebras_sdk":
        return call_judge_cerebras(client, cfg, messages)
    return call_judge_openai(client, cfg, messages)


def ensure_client(cfg: JudgeConfig):
    provider = normalize_provider_name(cfg.provider)
    if provider == "gemini":
        return ensure_gemini_client(cfg)
    if provider == "cerebras_sdk":
        return ensure_cerebras_client(cfg)
    return ensure_openai_client(cfg)


# ------------------------------- SCORE PROCESSING -------------------------------
def normalize_score(raw_score, is_baseline: bool = False) -> float:
    """Convert 1-5 score to 0-10 scale. Handle dict or scalar."""
    if isinstance(raw_score, dict):
        val = raw_score.get("baseline" if is_baseline else "candidate", 5)
    elif isinstance(raw_score, (int, float)):
        val = raw_score if not is_baseline else 5  # Assume baseline=5 for scalars
    else:
        val = 5
    return float(val) * 2  # Convert to 0-10 scale


def get_paired_scores(scores: Dict, metric: str) -> Tuple[float, float]:
    """Extract (candidate, baseline) scores on 0-10 scale."""
    raw = scores.get(metric, {})
    if isinstance(raw, dict):
        candidate = normalize_score(raw, is_baseline=False)
        baseline = normalize_score(raw, is_baseline=True)
    else:
        # Single value = candidate score, assume baseline = 10.0 (5*2)
        candidate = float(raw) * 2 if isinstance(raw, (int, float)) else 10.0
        baseline = 10.0
    return candidate, baseline


def interpret_score_diff(candidate: float, baseline: float, metric: str) -> str:
    """Generate short interpretation based on score difference."""
    diff = candidate - baseline
    
    # Special handling for verbosity (lower is better)
    if metric == "verbosity":
        diff = -diff  # Flip interpretation
    
    if diff >= 4:
        return "Strong win"
    elif diff >= 2:
        return "Clear advantage"
    elif diff >= 0.5:
        return "Slight edge"
    elif diff >= -0.5:
        return "Comparable"
    elif diff >= -2:
        return "Minor gap"
    elif diff >= -4:
        return "Notable weakness"
    else:
        return "Critical failure"


def compute_verdict_from_scores(scores: Dict) -> str:
    """
    Compute verdict from actual scores instead of trusting LLM's verdict.
    
    The LLM judge sometimes hallucinates the verdict field, saying "improved"
    when scores clearly show the candidate performed worse. This function
    computes the verdict based on the overall_quality score.
    
    Args:
        scores: Dict of metric -> {baseline: int, candidate: int}
    
    Returns:
        "improved", "regressed", or "equal"
    """
    overall = scores.get("overall_quality", {})
    if isinstance(overall, dict) and ("baseline" in overall) and ("candidate" in overall):
        baseline = overall.get("baseline", 3)
        candidate = overall.get("candidate", 3)
    else:
        # Do not silently mark malformed judge output as equal.
        return "error"
    
    if candidate > baseline:
        return "improved"
    elif candidate < baseline:
        return "regressed"
    else:
        return "equal"


def validate_paired_scores(scores: Dict) -> None:
    """
    Enforce a strict score schema for judge output integrity.
    """
    if not isinstance(scores, dict):
        raise ValueError("Judge output 'scores' must be an object.")

    missing = [metric for metric in METRIC_ORDER if metric not in scores]
    if missing:
        raise ValueError(f"Judge output missing metrics: {', '.join(missing)}")

    for metric in METRIC_ORDER:
        raw = scores.get(metric)
        if not isinstance(raw, dict):
            raise ValueError(f"Metric '{metric}' must be a paired score object.")
        for side in ("baseline", "candidate"):
            value = raw.get(side)
            if not isinstance(value, (int, float)):
                raise ValueError(f"Metric '{metric}.{side}' must be numeric.")
            if value < 1 or value > 5:
                raise ValueError(f"Metric '{metric}.{side}' must be in [1, 5].")


# ------------------------------- OUTPUT FORMATTING -------------------------------
def print_header(run_id: str, date_str: str, model_name: str, total: int):
    print("\n" + "=" * 80)
    print("                    LLM Judge Evaluation Results")
    print("=" * 80)
    print()
    print(f"Run ID          : {run_id}")
    print(f"Date            : {date_str}")
    print(f"Candidate Model : HOM-LLM(v2.0) ({model_name})")
    print(f"Baseline Model  : Cursor (Gemini 2.5 Flash)")
    print(f"Total Queries   : {total}")


def print_summary(records: List[Dict], run_id: str):
    verdicts = [r.get("verdict", "unknown") for r in records]
    improved = verdicts.count("improved")
    regressed = verdicts.count("regressed")
    equal = verdicts.count("equal")
    total = len(records)

    improved_pct = (improved / total * 100) if total else 0
    regressed_pct = (regressed / total * 100) if total else 0
    equal_pct = (equal / total * 100) if total else 0

    # Win rate = improved / (improved + regressed)
    contested = improved + regressed
    win_rate = (improved / contested * 100) if contested else 0

    print()
    print("-" * 22 + " SUMMARY " + "-" * 22)
    print(f"[+] Improved : {improved:3d} ({improved_pct:5.1f}%)")
    print(f"[-] Regressed: {regressed:3d} ({regressed_pct:5.1f}%)")
    print(f"[=] Equal    : {equal:3d} ({equal_pct:5.1f}%)")
    print()

    # Generate verdict
    if win_rate >= 80:
        verdict = "Strong performance advantage over baseline"
        strengths = "Consistent quality improvements across most queries"
        weaknesses = "Minor edge cases may need attention"
    elif win_rate >= 60:
        verdict = "Good performance, outperforming baseline"
        strengths = "Clear improvements in key areas"
        weaknesses = "Some regressions require investigation"
    elif win_rate >= 40:
        verdict = "Mixed results, roughly on par with baseline"
        strengths = "Competitive in several dimensions"
        weaknesses = "Inconsistent quality needs addressing"
    else:
        verdict = "Underperforming baseline - review required"
        strengths = "Some isolated improvements exist"
        weaknesses = "Systematic issues causing regressions"

    print(f"Overall Verdict: {verdict}")
    print(f"                  * {strengths}")
    print(f"                  * {weaknesses}")
    print()
    print(f"Candidate Win Rate (Improved / (Improved + Regressed)): {win_rate:.1f}%")


def print_score_table(scores: Dict, run_id: str, header: bool = True):
    """Print formatted score comparison table."""
    if header:
        print()
        print("-" * 27 + " SCORE COMPARISON (0-10) " + "-" * 27)
        print(f"{'Metric':<24} | {'HOM-LLM(v2.0)':<14} | {'Cursor Baseline':<15} | {'Interpretation':<20}")
        print("-" * 24 + "-+-" + "-" * 14 + "-+-" + "-" * 15 + "-+-" + "-" * 20)

    for metric in METRIC_ORDER:
        if metric not in scores:
            continue
        candidate, baseline = get_paired_scores(scores, metric)
        interp = interpret_score_diff(candidate, baseline, metric)
        display_name = METRIC_DISPLAY_NAMES.get(metric, metric)
        print(f"{display_name:<24} | {candidate:>14.1f} | {baseline:>15.1f} | {interp:<20}")


def print_query_detail(record: Dict, run_id: str):
    """Print detailed per-query result."""
    qid = record.get("query_id")
    verdict = record.get("verdict", "unknown")
    scores = record.get("scores", {})
    explanation = record.get("explanation", "N/A")
    key_diffs = record.get("key_differences", [])

    verdict_icon = "[+]" if verdict == "improved" else "[-]" if verdict == "regressed" else "[=]"
    print()
    print(f"Query {qid} {verdict_icon} {verdict.upper()}")
    
    print_score_table(scores, run_id)

    print()
    print(f"Explanation:")
    print(f"  {explanation}")

    if key_diffs:
        print()
        print("Key Differences:")
        for diff in key_diffs:
            if isinstance(diff, str):
                print(f"  * {diff}")


def print_average_scores(records: List[Dict], run_id: str):
    """Print overall average scores across all queries."""
    print()
    print("-" * 20 + " OVERALL AVERAGE SCORES (0-10) " + "-" * 20)
    print(f"{'Metric':<24} | {'HOM-LLM(v2.0)':<14} | {'Cursor Baseline':<15} | {'Interpretation':<20}")
    print("-" * 24 + "-+-" + "-" * 14 + "-+-" + "-" * 15 + "-+-" + "-" * 20)

    for metric in METRIC_ORDER:
        candidate_vals = []
        baseline_vals = []
        for r in records:
            scores = r.get("scores", {})
            if metric in scores:
                c, b = get_paired_scores(scores, metric)
                candidate_vals.append(c)
                baseline_vals.append(b)

        if candidate_vals:
            avg_candidate = sum(candidate_vals) / len(candidate_vals)
            avg_baseline = sum(baseline_vals) / len(baseline_vals)
            interp = interpret_score_diff(avg_candidate, avg_baseline, metric)
            display_name = METRIC_DISPLAY_NAMES.get(metric, metric)
            print(f"{display_name:<24} | {avg_candidate:>14.1f} | {avg_baseline:>15.1f} | {interp:<20}")


def print_final_summary(records: List[Dict]):
    """Print final interpretation summary."""
    # Compute overall metrics
    all_candidates = []
    all_baselines = []
    for r in records:
        scores = r.get("scores", {})
        for metric in METRIC_ORDER:
            if metric in scores:
                c, b = get_paired_scores(scores, metric)
                all_candidates.append(c)
                all_baselines.append(b)

    if all_candidates:
        avg_c = sum(all_candidates) / len(all_candidates)
        avg_b = sum(all_baselines) / len(all_baselines)
        diff = avg_c - avg_b

        if diff > 1:
            summary = (
                f"HOM-LLM demonstrates clear superiority with an average score advantage of {diff:.1f} points. "
                f"The system shows particular strength in semantic understanding and factual accuracy. "
                f"Continue current approach while monitoring edge cases."
            )
        elif diff > 0:
            summary = (
                f"HOM-LLM shows marginal improvement over baseline (+{diff:.1f} avg). "
                f"Performance is competitive but inconsistent across queries. "
                f"Focus on reducing variance and addressing regression cases."
            )
        else:
            summary = (
                f"HOM-LLM underperforms baseline by {abs(diff):.1f} points on average. "
                f"Critical review of context assembly and generation needed. "
                f"Prioritize fixing regressed queries before further development."
            )
    else:
        summary = "Insufficient data to generate summary."

    print()
    print("Final Summary Interpretation:")
    print(f"  {summary}")


# ------------------------------- MAIN -------------------------------
def main() -> None:
    configure_console_encoding()
    parser = argparse.ArgumentParser(description="LLM judge for HOM-LLM vs Cursor baseline.")
    parser.add_argument("--responses", type=Path, required=True, help="Path to responses JSONL from run_experiment")
    parser.add_argument("--baseline", type=Path, required=True, help="Path to cursor_baseline.json")
    parser.add_argument("--judge-config", type=Path, required=True, help="Path to judge_config.json")
    parser.add_argument(
        "--provider",
        type=str,
        choices=sorted(SUPPORTED_PROVIDERS),
        default=None,
        help="Optional provider override. If omitted, judge-config provider is used.",
    )
    parser.add_argument("--output", type=Path, help="Optional output path for judge_results.jsonl")
    parser.add_argument(
        "--append-output",
        action="store_true",
        help="Append to existing output path (default behavior is overwrite with de-dup).",
    )
    parser.add_argument(
        "--rpm", type=int, default=None,
        help="Rate limit: max requests per minute to LLM (overrides config, 0=unlimited)"
    )
    args = parser.parse_args()

    # Extract run_id from responses path
    run_id = args.responses.parent.name

    responses = read_jsonl(args.responses)
    baseline_payload = read_json(args.baseline)
    baseline_map = {item["query_id"]: item for item in baseline_payload.get("queries", [])}

    cfg = load_judge_config(args.judge_config, provider_override=args.provider)
    cfg.provider = normalize_provider_name(cfg.provider)

    key_pool_manager = None
    if cfg.provider == "gemini" and cfg.api_key_pool is not None:
        key_pool_manager = GeminiKeyPoolManager(cfg.api_key_pool)
        cfg.api_key = key_pool_manager.current_key()
        print(
            f"Gemini key rotation: enabled | pool={cfg.api_key_pool.pool_name} "
            f"| requests_per_key={cfg.api_key_pool.requests_per_key} "
            f"| current_key={key_pool_manager.current_name()}"
        )

    client = ensure_client(cfg)

    if args.output:
        output_path = args.output
    else:
        default_name = f"judge_results__{safe_filename_token(cfg.model)}.jsonl"
        output_path = args.responses.parent / default_name
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize rate limiter
    # CLI --rpm overrides config file setting
    rpm = args.rpm if args.rpm is not None else cfg.requests_per_minute
    rate_limiter = RateLimiter(requests_per_minute=rpm)
    if rate_limiter.enabled:
        print(f"Rate limit: {rpm} requests/minute (strict rolling window, +{rate_limiter.safety_seconds:.2f}s safety)")
    else:
        print("Rate limit: disabled (unlimited)")

    # Collect all records
    records: List[Dict] = []
    model_name = "unknown"

    print(f"Judge provider: {cfg.provider}")
    print(f"Judge model (config): {cfg.model}")
    request_params = [f"temperature={cfg.temperature}"]
    if cfg.top_p is not None:
        request_params.append(f"top_p={cfg.top_p}")
    if cfg.max_completion_tokens is not None:
        request_params.append(f"max_completion_tokens={cfg.max_completion_tokens}")
    if cfg.reasoning_effort:
        request_params.append(f"reasoning_effort={cfg.reasoning_effort}")
    request_params.append(f"stream={cfg.stream}")
    print(f"Judge request params: {', '.join(request_params)}")
    print(f"\nJudging {len(responses)} queries...")

    for idx, resp in enumerate(responses, 1):
        qid = resp.get("query_id")
        model_name = resp.get("model_name", model_name)

        base = baseline_map.get(qid)
        if not base:
            sys.stderr.write(f"[WARN] Missing baseline for query_id {qid}, skipping.\n")
            continue

        print(f"  [{idx}/{len(responses)}] Query {qid}...", end=" ", flush=True)

        messages = build_prompt(
            baseline_answer=base.get("answer", ""),
            candidate_answer=resp.get("answer_text", ""),
            query_text=resp.get("query_text", ""),
        )

        while True:
            try:
                # Apply rate limiting before each LLM call
                wait_time = rate_limiter.acquire()
                if wait_time > 0:
                    # Show wait indicator for long waits
                    if wait_time > 1.0:
                        print(f"(waited {wait_time:.1f}s) ", end="", flush=True)

                judged, judge_model_used = call_judge(client, cfg, messages)
                # IMPORTANT: Compute verdict from scores, not LLM's verdict field.
                # The LLM sometimes hallucinates the verdict, saying "improved" when
                # the scores clearly show the candidate performed worse.
                scores = judged.get("scores", {})
                validate_paired_scores(scores)
                verdict = compute_verdict_from_scores(scores)
                llm_verdict = judged.get("verdict", "unknown")
                if verdict != llm_verdict:
                    # Log when we override the LLM's verdict
                    sys.stderr.write(f"[WARN] Query {qid}: LLM said '{llm_verdict}' but scores show '{verdict}'\n")
                verdict_symbol = '[+]' if verdict == 'improved' else '[-]' if verdict == 'regressed' else '[=]'
                print(f"{verdict_symbol} {verdict}")
                if key_pool_manager is not None:
                    previous_key_name = key_pool_manager.current_name()
                    key_pool_manager.mark_success()
                    next_key_name = key_pool_manager.current_name()
                    if next_key_name != previous_key_name:
                        sys.stderr.write(
                            f"[KEY_ROTATION] Completed quota for '{previous_key_name}', next key is '{next_key_name}'.\n"
                        )
                        cfg.api_key = key_pool_manager.current_key()
                        client = ensure_client(cfg)
                break
            except Exception as exc:
                if key_pool_manager is not None and _is_quota_exhausted_error(exc):
                    exhausted_name = key_pool_manager.current_name()
                    try:
                        key_pool_manager.mark_quota_exhausted()
                        replacement_name = key_pool_manager.current_name()
                        cfg.api_key = key_pool_manager.current_key()
                        client = ensure_client(cfg)
                        sys.stderr.write(
                            f"[KEY_ROTATION] Quota exhausted for '{exhausted_name}', switched to '{replacement_name}'.\n"
                        )
                        continue
                    except Exception as rotate_exc:
                        sys.stderr.write(f"ERROR: {rotate_exc}\n")
                        break

                sys.stderr.write(f"ERROR: {exc}\n")
                break
        else:
            continue

        if "verdict" not in locals():
            continue

        record = {
            "query_id": qid,
            "query_text": resp.get("query_text"),
            "candidate_model": resp.get("model_name"),
            "candidate_provider": resp.get("provider"),
            "baseline_system": baseline_payload.get("metadata", {}).get("system", "Cursor"),
            "judge_provider": cfg.provider,
            "judge_model": judge_model_used,
            "judge_model_config": cfg.model,
            "scores": scores,
            "verdict": verdict,  # Use computed verdict, not LLM's
            "llm_verdict": llm_verdict,  # Store LLM's original verdict for audit
            "explanation": judged.get("explanation"),
            "key_differences": judged.get("key_differences"),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        records.append(record)

    if not records:
        print("\nNo queries were judged successfully.")
        return

    if args.append_output and output_path.exists():
        existing = read_jsonl(output_path)
        merged = dedupe_records_by_query_id(existing + records)
    else:
        merged = dedupe_records_by_query_id(records)
    write_jsonl(output_path, merged, mode="w")

    # Format date
    date_str = datetime.now().strftime("%B %d, %Y")

    # ====================== PRINT FULL REPORT ======================
    print_header(run_id, date_str, model_name, len(merged))
    print_summary(merged, run_id)

    # Separate by verdict
    regressed = [r for r in merged if r.get("verdict") == "regressed"]
    improved = [r for r in merged if r.get("verdict") == "improved"]
    equal = [r for r in merged if r.get("verdict") == "equal"]

    # Print regressions first (priority)
    if regressed:
        print()
        print()
        print("-" * 18 + " DETAILED PER-QUERY RESULTS " + "-" * 18)
        print()
        print("=== CRITICAL REGRESSIONS (Review First) ===")
        for r in regressed:
            print_query_detail(r, run_id)

    # Then improvements
    if improved:
        print()
        print("=== IMPROVEMENTS ===")
        for r in improved:
            print_query_detail(r, run_id)

    # Equal last (optional)
    if equal:
        print()
        print("=== EQUAL ===")
        for r in equal:
            print_query_detail(r, run_id)

    # Overall averages
    print_average_scores(merged, run_id)

    # Final interpretation
    print_final_summary(merged)

    # Footer
    print()
    print("=" * 80)
    print(f"Judgment results saved to: {output_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()


