"""
Stage 2 — Semantic refinement via frozen embedding intent clustering (spec §4.2, §5).

Only when Stage 1 is SHALLOW_OK. Detects implicit explanatory/illustrative intent.
May only upgrade; never downgrade.
"""

from __future__ import annotations

from homllm.explanation_gap.constants import EMBEDDING_UPGRADE_THRESHOLD
from homllm.explanation_gap.interfaces import (
    DepthLabelType,
    SignalOutput,
    max_severity,
)


def cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Frozen cosine similarity."""
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = (sum(x * x for x in a)) ** 0.5
    nb = (sum(y * y for y in b)) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def embedding_refinement(
    current_label: DepthLabelType,
    query_embedding: tuple[float, ...] | None,
    illustrative_centroid: tuple[float, ...] | None,
    explanatory_centroid: tuple[float, ...] | None,
    factual_centroid: tuple[float, ...] | None,
) -> tuple[DepthLabelType, str, list[SignalOutput]]:
    """
    Stage 2: only upgrades. When current_label is SHALLOW_OK and embedding suggests
    explanatory or illustrative intent, upgrade to DETAILED_REQUIRED or EXAMPLE_RECOMMENDED.
    """
    if current_label != "SHALLOW_OK":
        # Stage 2 only refines when Stage 1 is silent (SHALLOW_OK)
        sig = SignalOutput(
            signal_name="embedding_refinement",
            label=None,
            trigger="Embedding(skip_not_shallow)",
            score_or_note="",
        )
        return current_label, "Embedding(skip)", [sig]

    if (
        query_embedding is None
        or illustrative_centroid is None
        or explanatory_centroid is None
        or factual_centroid is None
    ):
        sig = SignalOutput(
            signal_name="embedding_refinement",
            label=None,
            trigger="Embedding(unavailable)",
            score_or_note="",
        )
        return current_label, "Embedding(unavailable)", [sig]

    sim_ill = cosine_similarity(query_embedding, illustrative_centroid)
    sim_exp = cosine_similarity(query_embedding, explanatory_centroid)
    sim_fact = cosine_similarity(query_embedding, factual_centroid)

    if sim_ill >= EMBEDDING_UPGRADE_THRESHOLD and sim_ill >= sim_exp and sim_ill >= sim_fact:
        upgraded = max_severity("SHALLOW_OK", "EXAMPLE_RECOMMENDED")
        sig = SignalOutput(
            signal_name="embedding_refinement",
            label=upgraded,
            trigger="Embedding(illustrative)",
            score_or_note=f"sim_illustrative={sim_ill:.3f}",
        )
        return upgraded, "Embedding(illustrative)", [sig]
    if sim_exp >= EMBEDDING_UPGRADE_THRESHOLD and sim_exp >= sim_fact:
        upgraded = max_severity("SHALLOW_OK", "DETAILED_REQUIRED")
        sig = SignalOutput(
            signal_name="embedding_refinement",
            label=upgraded,
            trigger="Embedding(explanatory)",
            score_or_note=f"sim_explanatory={sim_exp:.3f}",
        )
        return upgraded, "Embedding(explanatory)", [sig]

    sig = SignalOutput(
        signal_name="embedding_refinement",
        label=None,
        trigger="Embedding(factual_or_below_threshold)",
        score_or_note=f"sim_factual={sim_fact:.3f}",
    )
    return current_label, "Embedding(no_upgrade)", [sig]


__all__ = ["embedding_refinement", "cosine_similarity"]
