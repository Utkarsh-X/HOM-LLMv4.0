"""
Gemini API smoke test (LOCAL ONLY; gitignored).

Edit the config below, then run:
  python gemini_smoketest.py
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GeminiSmokeTestConfig:
    # NOTE: You pasted a real API key into this file. Even though this file is gitignored,
    # rotate/revoke that key now and replace it here with the new one.
    api_key: str = "AIzaSyCeZJweypg_R6o_0JXmtZc7JgeTe2ZF6Fc"

    # Accepts either short names (e.g. "gemini-1.5-flash") or full resource names
    # (e.g. "models/gemini-1.5-flash"). We'll normalize automatically.
    model: str = "gemini-1.5-flash"
    temperature: float = 0.0
    max_output_tokens: int = 256
    prompt: str = "Reply with exactly: OK"

    # Debug: print models visible to this key (slow if many).
    list_models: bool = False


def _dump(obj: Any) -> str:
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True)
    except Exception:
        return repr(obj)

def _normalize_model_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return name
    # google-genai accepts both "models/<id>" and "<id>" in many cases, but to reduce 404s
    # across endpoints we normalize "<id>" -> "models/<id>".
    if "/" not in name:
        return f"models/{name}"
    return name


def main() -> int:
    from google import genai

    cfg = GeminiSmokeTestConfig()
    if not cfg.api_key or "PASTE_YOUR" in cfg.api_key:
        print("ERROR: set GeminiSmokeTestConfig.api_key in this file.")
        return 2

    client = genai.Client(api_key=cfg.api_key)

    if cfg.list_models:
        try:
            print("AVAILABLE_MODELS (debug):")
            for m in client.models.list():
                print(f"- {getattr(m, 'name', m)}")
            print()
        except Exception as e:
            print(f"[WARN] models.list failed: {type(e).__name__}: {e}")
            print()

    model_name = _normalize_model_name(cfg.model)
    t0 = time.perf_counter()
    try:
        resp = client.models.generate_content(
            model=model_name,
            contents=cfg.prompt,
            config={
                "temperature": cfg.temperature,
                "max_output_tokens": cfg.max_output_tokens,
            },
        )
    except Exception as e:
        dt_ms = (time.perf_counter() - t0) * 1000
        print(f"SMOKETEST FAIL model={model_name} dt_ms={dt_ms:.0f}")
        print(f"ERROR: {type(e).__name__}: {e}")
        print()
        print("HINTS:")
        print("- If you see 404/NotFound: your key may not have access to that model name.")
        print("- Flip `list_models=True` to print model names visible to your key.")
        print("- Try a newer generally-available model like `gemini-2.0-flash` or `gemini-2.5-flash`.")
        return 1

    dt_ms = (time.perf_counter() - t0) * 1000
    text = getattr(resp, "text", None)
    print(f"SMOKETEST OK model={model_name} dt_ms={dt_ms:.0f}")
    print("RESPONSE_TEXT:")
    print(text if text is not None else "(no .text field)")
    print()
    print("RAW_RESPONSE (debug):")
    print(_dump(getattr(resp, "__dict__", {"repr": repr(resp)})))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
