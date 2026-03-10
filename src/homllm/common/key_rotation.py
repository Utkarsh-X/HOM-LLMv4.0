"""
Gemini API Key Rotation Manager.

Manages a pool of Gemini API keys with automatic rotation after each key
reaches its request limit (default: 20 requests per key).

Usage tracking is persisted to configs/key_usage_state.json so that counts
survive process restarts.

Key pool is defined in configs/secrets.yaml under:
    api_keys:
      gemini_pool:
        requests_per_key: 20
        daily_reset_hour: 0       # auto-reset at midnight local time
        keys:
          - name: "main-dev"
            key: "AIza..."
          - name: "backup-1"
            key: "AIza..."

Also supports the legacy plain-string format (backward compatible):
    keys:
      - "AIza..."

If gemini_pool is absent, falls back to the single api_keys.gemini key
with no rotation (backward compatible).

Auto-reset behavior:
  If daily_reset_hour is set (0-23), the system checks on every startup
  and every get_key() call whether a daily reset window has passed.
  If yes, all counters are automatically zeroed out — even if the PC was
  off during the actual reset hour. This is timestamp-based, not timer-based.
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default paths (relative to project root)
_SECRETS_FILENAME = "configs/secrets.yaml"
_STATE_FILENAME = "configs/key_usage_state.json"
_DEFAULT_LIMIT = 20


class AllKeysExhaustedError(RuntimeError):
    """Raised when every key in the pool has hit its request limit."""
    pass


class KeyRotationManager:
    """
    Thread-safe, persistent Gemini API key rotator.

    Algorithm:
      1. Load pool from secrets.yaml -> api_keys.gemini_pool.keys
      2. Load state  from key_usage_state.json (auto-created)
      3. Check if daily quota reset has passed -> auto-reset if so
      4. On get_key():
           - Find the first key whose count < limit
           - Return that key
      5. On record_usage():
           - Increment the current key's counter
           - Persist state to disk
      6. On key exhaustion -> advance to next key
      7. If ALL keys exhausted -> raise AllKeysExhaustedError
    """

    _instance: Optional["KeyRotationManager"] = None
    _lock = threading.Lock()

    def __init__(self, project_root: Optional[Path] = None):
        if project_root is None:
            # Derive from CWD or this file's location
            project_root = Path.cwd()
            # Also try from file location (4 levels up from src/homllm/common/)
            alt = Path(__file__).resolve().parent.parent.parent.parent
            if (alt / "configs" / "secrets.yaml").exists():
                project_root = alt

        self._project_root = project_root
        self._secrets_path = project_root / _SECRETS_FILENAME
        self._state_path = project_root / _STATE_FILENAME
        self._mutex = threading.Lock()

        # Pool configuration
        self._keys: list[str] = []
        self._names: list[str] = []   # Human-readable names for each key
        self._limit: int = _DEFAULT_LIMIT
        self._current_index: int = 0
        self._usage_counts: list[int] = []
        self._daily_reset_hour: Optional[int] = None  # None = no auto-reset
        self._last_reset_date: Optional[str] = None    # ISO date of last reset

        # Whether pool mode is active (vs single-key fallback)
        self._pool_mode: bool = False

        self._load_pool()
        self._load_state()
        self._check_daily_reset()  # Auto-reset on startup if quota window passed

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_key(self) -> str:
        """
        Return the current active API key.

        If the current key has reached its limit, advance to the next key.
        Raises AllKeysExhaustedError if no keys remain.
        """
        with self._mutex:
            # Check daily reset before returning a key
            self._check_daily_reset_locked()

            if not self._pool_mode:
                # Single-key fallback: return the one key, no rotation
                if self._keys:
                    return self._keys[0]
                raise AllKeysExhaustedError("No Gemini API keys configured.")

            # Find a key that hasn't hit its limit
            while self._current_index < len(self._keys):
                if self._usage_counts[self._current_index] < self._limit:
                    return self._keys[self._current_index]
                # This key is exhausted, advance
                exhausted_name = self._names[self._current_index]
                next_idx = self._current_index + 1
                next_name = self._names[next_idx] if next_idx < len(self._names) else "NONE"
                logger.info(
                    "[KEY_ROTATION] Key '%s' (slot %d) exhausted (%d/%d). "
                    "Switching to '%s' (slot %d).",
                    exhausted_name,
                    self._current_index,
                    self._usage_counts[self._current_index],
                    self._limit,
                    next_name,
                    next_idx,
                )
                self._current_index += 1
                self._save_state()

            raise AllKeysExhaustedError(
                f"All {len(self._keys)} Gemini API keys exhausted "
                f"(limit={self._limit} requests/key). "
                f"Add more keys to configs/secrets.yaml under gemini_pool.keys."
            )

    def record_usage(self) -> dict:
        """
        Record one API request against the current key.

        Returns a status dict with current slot info for telemetry/logging.
        """
        with self._mutex:
            if not self._pool_mode or not self._keys:
                return {"pool_mode": False}

            idx = self._current_index
            if idx < len(self._usage_counts):
                self._usage_counts[idx] += 1
                self._save_state()

                remaining = self._limit - self._usage_counts[idx]
                total_remaining = sum(
                    max(0, self._limit - c) for c in self._usage_counts
                )
                name = self._names[idx]

                status = {
                    "pool_mode": True,
                    "current_slot": idx,
                    "current_name": name,
                    "slot_usage": self._usage_counts[idx],
                    "slot_limit": self._limit,
                    "slot_remaining": remaining,
                    "total_keys": len(self._keys),
                    "total_remaining_requests": total_remaining,
                }

                logger.info(
                    "[KEY_ROTATION] '%s' (slot %d): %d/%d used (%d remaining). "
                    "Pool: %d requests remaining across %d keys.",
                    name,
                    idx,
                    self._usage_counts[idx],
                    self._limit,
                    remaining,
                    total_remaining,
                    len(self._keys),
                )

                return status

            return {"pool_mode": True, "error": "index_out_of_range"}

    def get_status(self) -> dict:
        """Return full pool status for diagnostics."""
        with self._mutex:
            if not self._pool_mode:
                return {"pool_mode": False, "total_keys": len(self._keys)}

            slots = []
            for i, key in enumerate(self._keys):
                used = self._usage_counts[i] if i < len(self._usage_counts) else 0
                name = self._names[i]
                slots.append({
                    "slot": i,
                    "name": name,
                    "key_prefix": key[:8] + "...",  # Redact for safety
                    "used": used,
                    "limit": self._limit,
                    "remaining": max(0, self._limit - used),
                    "active": i == self._current_index,
                    "exhausted": used >= self._limit,
                })

            status = {
                "pool_mode": True,
                "current_slot": self._current_index,
                "current_name": self._names[self._current_index] if self._current_index < len(self._names) else "N/A",
                "total_keys": len(self._keys),
                "limit_per_key": self._limit,
                "total_remaining": sum(s["remaining"] for s in slots),
                "slots": slots,
            }

            # Auto-reset info
            if self._daily_reset_hour is not None:
                status["daily_reset_hour"] = self._daily_reset_hour
                status["last_reset_date"] = self._last_reset_date
                # Calculate next reset
                now = datetime.now()
                today_reset = now.replace(
                    hour=self._daily_reset_hour, minute=0, second=0, microsecond=0
                )
                if now >= today_reset:
                    next_reset = today_reset.replace(day=today_reset.day + 1)
                else:
                    next_reset = today_reset
                status["next_reset"] = next_reset.strftime("%Y-%m-%d %H:%M")
            else:
                status["daily_reset_hour"] = None
                status["next_reset"] = "manual only"

            return status

    def reset(self) -> None:
        """Reset all usage counters to zero. Use after quota resets."""
        with self._mutex:
            self._current_index = 0
            self._usage_counts = [0] * len(self._keys)
            self._last_reset_date = datetime.now().strftime("%Y-%m-%d")
            self._save_state()
            logger.info("[KEY_ROTATION] All counters reset to zero.")

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------

    @classmethod
    def instance(cls, project_root: Optional[Path] = None) -> "KeyRotationManager":
        """Get or create the singleton instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(project_root)
            assert cls._instance is not None  # For type checker
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        with cls._lock:
            cls._instance = None

    # ------------------------------------------------------------------
    # Daily auto-reset logic
    # ------------------------------------------------------------------

    def _check_daily_reset(self) -> None:
        """Check and apply daily reset (called on startup, outside mutex)."""
        with self._mutex:
            self._check_daily_reset_locked()

    def _check_daily_reset_locked(self) -> None:
        """
        Check if the daily quota reset window has passed.

        Logic:
          - If daily_reset_hour is not configured, do nothing.
          - Compute today's reset moment: today at daily_reset_hour:00.
          - If NOW is past that moment AND the last reset was BEFORE that
            moment (or never), reset all counters.
          - This works even if the PC was off during the reset hour:
            the next time the system runs and calls get_key(), this
            check fires and resets automatically.
        """
        if self._daily_reset_hour is None:
            return

        if not self._pool_mode:
            return

        now = datetime.now()
        today_reset = now.replace(
            hour=self._daily_reset_hour, minute=0, second=0, microsecond=0
        )

        # Are we past today's reset time?
        if now < today_reset:
            # Not yet past the reset hour today — no reset needed
            return

        # We are past today's reset hour. Was the last reset already today?
        today_date = today_reset.strftime("%Y-%m-%d")
        if self._last_reset_date == today_date:
            # Already reset today
            return

        # Reset is needed!
        old_counts = list(self._usage_counts)
        self._current_index = 0
        self._usage_counts = [0] * len(self._keys)
        self._last_reset_date = today_date
        self._save_state()

        total_was_used = sum(old_counts)
        logger.info(
            "[KEY_ROTATION] AUTO-RESET: Daily quota window passed "
            "(reset_hour=%d:00, last_reset=%s). "
            "Cleared %d used requests across %d keys. All slots reset to 0.",
            self._daily_reset_hour,
            self._last_reset_date,
            total_was_used,
            len(self._keys),
        )

    # ------------------------------------------------------------------
    # Pool loading
    # ------------------------------------------------------------------

    def _load_pool(self) -> None:
        """Load key pool from secrets.yaml."""
        try:
            import yaml
        except ImportError:
            logger.warning("[KEY_ROTATION] PyYAML not installed; key rotation disabled.")
            return

        if not self._secrets_path.exists():
            logger.warning(
                "[KEY_ROTATION] %s not found; key rotation disabled.", self._secrets_path
            )
            return

        try:
            with open(self._secrets_path, "r", encoding="utf-8") as f:
                secrets = yaml.safe_load(f)
        except Exception as e:
            logger.error("[KEY_ROTATION] Failed to load secrets: %s", e)
            return

        if not secrets or "api_keys" not in secrets:
            return

        api_keys = secrets["api_keys"]

        # Check for pool format first
        pool_config = api_keys.get("gemini_pool")
        if pool_config and isinstance(pool_config, dict):
            raw_keys = pool_config.get("keys", [])
            if raw_keys and isinstance(raw_keys, list):
                valid_keys = []
                valid_names = []

                for i, entry in enumerate(raw_keys):
                    if isinstance(entry, dict):
                        # Named format: {name: "...", key: "..."}
                        key_val = entry.get("key", "")
                        name_val = entry.get("name", f"key-{i}")
                        if key_val and key_val != "your_gemini_api_key_here":
                            valid_keys.append(key_val)
                            valid_names.append(name_val)
                    elif isinstance(entry, str):
                        # Legacy plain-string format
                        if entry and entry != "your_gemini_api_key_here":
                            valid_keys.append(entry)
                            valid_names.append(f"key-{i}")

                if valid_keys:
                    self._keys = valid_keys
                    self._names = valid_names
                    self._limit = int(pool_config.get("requests_per_key", _DEFAULT_LIMIT))
                    self._pool_mode = True
                    self._usage_counts = [0] * len(self._keys)

                    # Daily reset config
                    reset_hour = pool_config.get("daily_reset_hour")
                    if reset_hour is not None:
                        self._daily_reset_hour = int(reset_hour)

                    logger.info(
                        "[KEY_ROTATION] Pool mode ACTIVE: %d keys [%s], "
                        "%d requests/key, %d total capacity. "
                        "Auto-reset: %s",
                        len(self._keys),
                        ", ".join(self._names),
                        self._limit,
                        len(self._keys) * self._limit,
                        f"daily at {self._daily_reset_hour}:00"
                        if self._daily_reset_hour is not None
                        else "manual only",
                    )
                    return

        # Fallback: single key
        single_key = api_keys.get("gemini")
        if single_key and single_key != "your_gemini_api_key_here":
            self._keys = [single_key]
            self._names = ["default"]
            self._pool_mode = False
            self._usage_counts = [0]
            logger.info("[KEY_ROTATION] Single-key mode (no rotation).")

    def _load_state(self) -> None:
        """Load persisted usage state from JSON file."""
        if not self._state_path.exists():
            return

        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception as e:
            logger.warning("[KEY_ROTATION] Could not load state: %s", e)
            return

        if not isinstance(state, dict):
            return

        saved_index = state.get("current_index", 0)
        saved_counts = state.get("usage_counts", [])
        saved_key_count = state.get("key_count", 0)
        self._last_reset_date = state.get("last_reset_date")

        # Only restore state if the key count matches (keys weren't added/removed)
        if saved_key_count == len(self._keys) and len(saved_counts) == len(self._keys):
            self._current_index = min(saved_index, len(self._keys) - 1) if self._keys else 0
            self._usage_counts = saved_counts
            active_name = self._names[self._current_index] if self._current_index < len(self._names) else "?"
            logger.info(
                "[KEY_ROTATION] Restored state: active='%s' (slot %d), counts=%s, last_reset=%s",
                active_name,
                self._current_index,
                self._usage_counts,
                self._last_reset_date or "never",
            )
        else:
            logger.info(
                "[KEY_ROTATION] Key pool changed (%d -> %d keys). Resetting counters.",
                saved_key_count,
                len(self._keys),
            )
            self._current_index = 0
            self._usage_counts = [0] * len(self._keys)
            self._save_state()

    def _save_state(self) -> None:
        """Persist current state to JSON file."""
        state = {
            "current_index": self._current_index,
            "usage_counts": self._usage_counts,
            "key_count": len(self._keys),
            "key_names": self._names,
            "limit_per_key": self._limit,
            "last_reset_date": self._last_reset_date,
        }
        try:
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error("[KEY_ROTATION] Failed to save state: %s", e)
