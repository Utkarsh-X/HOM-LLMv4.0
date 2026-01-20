# indexes_maker.py
# DEPRECATED: Use runtime/index_repo.py instead
# This file is kept for backward compatibility but will be removed in future versions.

import sys
from pathlib import Path

# Redirect to new runtime entrypoint
if __name__ == "__main__":
    print("Warning: indexes_maker.py is deprecated. Use: python runtime/index_repo.py --repo <path>")
    print("Redirecting to runtime/index_repo.py...\n")
    
    # Default repo path (can be overridden via command line)
    default_repo = Path(r"D:\HOM-LLM(v2.0)\test_repo")
    
    import subprocess
    cmd = [
        sys.executable,
        str(Path(__file__).parent / "runtime" / "index_repo.py"),
        "--repo",
        str(default_repo),
    ]
    
    # Add any additional args
    if len(sys.argv) > 1:
        cmd.extend(sys.argv[1:])
    
    sys.exit(subprocess.call(cmd))