"""
HuggingFace cache helpers.

Transformers can still make hub API calls even with `local_files_only=True`
when given a repo-id string. The reliable offline path is to pass a local
snapshot directory (from the HF cache) into `from_pretrained(...)`.
"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_snapshot_dir(model_id_or_path: str) -> Path | None:
    """
    Resolve a HF model repo id (e.g. "Org/Repo") to a local snapshot directory.

    Returns:
        - Path to snapshot dir if present locally
        - Path to model_id_or_path if it is already a local directory
        - None if not found
    """
    if not model_id_or_path:
        return None

    direct = Path(model_id_or_path)
    if direct.exists() and direct.is_dir():
        return direct

    hf_home = os.environ.get("HF_HOME")
    hf_hub_cache = os.environ.get("HF_HUB_CACHE")
    if hf_hub_cache:
        hub_dir = Path(hf_hub_cache)
    elif hf_home:
        hub_dir = Path(hf_home) / "hub"
    else:
        hub_dir = Path.home() / ".cache" / "huggingface" / "hub"

    model_dir_name = "models--" + model_id_or_path.replace("/", "--")
    model_dir = hub_dir / model_dir_name
    if not model_dir.exists():
        return None

    # Prefer the ref pointed to by refs/main when available.
    ref_main = model_dir / "refs" / "main"
    if ref_main.exists():
        commit = ref_main.read_text(encoding="utf-8").strip()
        if commit:
            snap = model_dir / "snapshots" / commit
            if snap.exists():
                return snap

    snaps_dir = model_dir / "snapshots"
    if not snaps_dir.exists():
        return None

    snapshots = [p for p in snaps_dir.iterdir() if p.is_dir()]
    if not snapshots:
        return None

    # Most-recent snapshot.
    snapshots.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return snapshots[0]


__all__ = ["resolve_snapshot_dir"]

