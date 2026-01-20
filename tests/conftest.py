"""
Pytest bootstrap for HOM-LLM.

Ensures <project_root>/src is on sys.path so `homllm` can be imported
without requiring `pip install -e .`.
"""

import sys
from pathlib import Path

# Resolve paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"

# Idempotent insertion
src_str = str(SRC_PATH)
if src_str not in sys.path:
    sys.path.insert(0, src_str)
