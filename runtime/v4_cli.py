#!/usr/bin/env python3
"""Repo-root friendly entrypoint for the HOM-LLM v4 CLI."""
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import bootstrap  # noqa: F401

from homllm_v4.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
