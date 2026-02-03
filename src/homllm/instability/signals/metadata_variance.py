"""
Context Metadata Variance (spec § Signal 2).

Variance in file-type distribution, diversity metrics. High variance → UNSTABLE_CONTEXT.
"""

from __future__ import annotations

import os

from homllm.instability.interfaces import PrimaryLabelType, RunRecord
from homllm.instability.utils import normalized_variance


def metadata_variance(runs: tuple[RunRecord, ...]) -> tuple[float, PrimaryLabelType | None]:
    """
    Instability from context metadata variance across runs.
    Variance in file-type distribution and run size. High → UNSTABLE_CONTEXT.
    """
    if len(runs) < 2:
        return 0.0, None
    n_exts = tuple(
        float(len({os.path.splitext(p)[1].lower() for p in r.file_paths}))
        for r in runs
    )
    n_files = tuple(float(len(r.file_paths)) for r in runs)
    v_ext = normalized_variance(n_exts)
    v_files = normalized_variance(n_files)
    score = min(1.0, (v_ext + v_files) / 2.0)
    label: PrimaryLabelType | None = "UNSTABLE_CONTEXT" if score > 0.5 else None
    return score, label
