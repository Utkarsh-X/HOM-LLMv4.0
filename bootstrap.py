# bootstrap.py
"""
Runtime bootstrap for HOM-LLM.

Adds <project_root>/src to sys.path so the package can be imported
without pip install -e .

Usage:
    import bootstrap  # Must be first import
    from homllm.common.config import Config

This module is:
- Cross-platform (Windows, Linux, macOS)
- Deterministic (uses pathlib.resolve())
- Idempotent (safe to import multiple times)
- Packaging-tool agnostic (no setuptools/pip required)
- Python 3.14 compatible (stdlib only)
"""

import sys
from pathlib import Path

# Module-level constants (exported for use by other scripts)
PROJECT_ROOT: Path = Path(__file__).resolve().parent
SRC_PATH: Path = PROJECT_ROOT / "src"

# Idempotent path insertion
_src_str = str(SRC_PATH)
if _src_str not in sys.path:
    sys.path.insert(0, _src_str)
