"""Pytest bootstrap: make the repository root importable regardless of CWD.

The benchmark runs verification with pytest from the workspace root. This
conftest guarantees package imports (e.g. ``security.hashing``) resolve even
when the test suite is invoked without an explicit PYTHONPATH.
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
