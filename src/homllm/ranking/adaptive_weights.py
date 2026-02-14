"""Adaptive weight modulation based on signal profile."""

from __future__ import annotations

from dataclasses import dataclass

from homllm.ranking.signal_profile import SignalProfile


@dataclass(frozen=True)
class WeightProfile:
    w_base: float
    w_struct: float
    w_rerank: float
    w_diversity: float


def compute_adaptive_weights(
    base_w_base: float,
    base_w_struct: float,
    base_w_rerank: float,
    profile: SignalProfile,
    reranker_fired: bool,
) -> WeightProfile:
    w_base = base_w_base

    connectivity_factor = 0.0
    if profile.avg_graph_distance >= 0:
        if profile.avg_graph_distance < 1.5:
            connectivity_factor = 1.0
        elif profile.avg_graph_distance < 3.0:
            connectivity_factor = 0.5

    w_struct = min(1.0, base_w_struct + 0.2 * connectivity_factor)

    if not reranker_fired:
        w_rerank = 0.0
    else:
        if profile.margin > 0.2:
            w_rerank = min(1.0, base_w_rerank)
        else:
            w_rerank = min(1.0, max(base_w_rerank, 0.5))

    if profile.file_entropy > 0.7:
        w_diversity = 0.3
    elif profile.file_entropy >= 0.4:
        w_diversity = 0.1
    else:
        w_diversity = 0.0

    return WeightProfile(
        w_base=w_base,
        w_struct=w_struct,
        w_rerank=w_rerank,
        w_diversity=w_diversity,
    )


__all__ = ["WeightProfile", "compute_adaptive_weights"]
