#!/usr/bin/env python3
"""
Gemini API Key Pool Status Checker.

Run this anytime to see which key is active, how many requests
each key has used, and how many remain.

Usage:
  python configs/key_status.py           # Show status
  python configs/key_status.py --reset   # Reset all counters to zero
"""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from homllm.common.key_rotation import KeyRotationManager


def print_status():
    """Print a formatted status dashboard."""
    KeyRotationManager.reset_instance()
    mgr = KeyRotationManager.instance(ROOT)
    status = mgr.get_status()

    if not status.get("pool_mode"):
        print("  Mode: Single-key (no rotation)")
        print("  No pool configured. Add gemini_pool to configs/secrets.yaml.")
        return

    total_keys = status["total_keys"]
    limit = status["limit_per_key"]
    total_cap = total_keys * limit
    total_used = total_cap - status["total_remaining"]
    current_name = status["current_name"]

    print()
    print("=" * 62)
    print("  GEMINI API KEY POOL STATUS")
    print("=" * 62)
    print()
    print(f"  Active Key:       {current_name} (slot {status['current_slot']})")
    print(f"  Keys in Pool:     {total_keys}")
    print(f"  Limit per Key:    {limit} requests")
    print(f"  Total Capacity:   {total_cap} requests")
    print(f"  Total Used:       {total_used} requests")
    print(f"  Total Remaining:  {status['total_remaining']} requests")
    print()

    # Auto-reset info
    reset_hour = status.get("daily_reset_hour")
    if reset_hour is not None:
        last_reset = status.get("last_reset_date", "never")
        next_reset = status.get("next_reset", "?")
        print(f"  Auto-Reset:       Every day at {reset_hour}:00 local time")
        print(f"  Last Reset:       {last_reset}")
        print(f"  Next Reset:       {next_reset}")
    else:
        print(f"  Auto-Reset:       OFF (manual only: --reset)")
    print()

    print("-" * 62)
    print(f"  {'Slot':<6} {'Name':<16} {'Used':<10} {'Remaining':<12} {'Status'}")
    print("-" * 62)

    for s in status["slots"]:
        if s["active"]:
            marker = ">>> ACTIVE"
        elif s["exhausted"]:
            marker = "    DONE"
        else:
            marker = "    waiting"

        bar_len = 20
        filled = int((s["used"] / s["limit"]) * bar_len) if s["limit"] > 0 else 0
        bar = "#" * filled + "." * (bar_len - filled)

        print(
            f"  {s['slot']:<6} {s['name']:<16} "
            f"{s['used']}/{s['limit']:<7} "
            f"{s['remaining']:<12} "
            f"{marker}"
        )
        print(f"         [{bar}]  {s['key_prefix']}")

    print("-" * 62)
    print()


def reset_counters():
    """Reset all usage counters."""
    KeyRotationManager.reset_instance()
    mgr = KeyRotationManager.instance(ROOT)
    mgr.reset()
    print("  All key usage counters have been reset to zero.")
    print()
    print_status()


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset_counters()
    else:
        print_status()
