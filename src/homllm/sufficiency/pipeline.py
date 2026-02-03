"""
Intent-Gated Sufficiency Layer — Pipeline (plan §4).

Read-only diagnostic: measure sufficiency, emit verdict and attribution.
Does not influence generation, retrieval, ranking, or prompts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homllm.sufficiency.intent import classify_intent
from homllm.sufficiency.interfaces import SufficiencyResult
from homllm.sufficiency.signals import (
    compute_rule_signal,
    compute_semantic_signal,
    compute_structural_signal,
)
from homllm.sufficiency.veto import resolve_veto

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact
    from homllm.indexer.embedder import QwenEmbedder


def run_sufficiency(
    query: str,
    context_artifact: "ContextArtifact",
    embedder: "QwenEmbedder | None" = None,
) -> SufficiencyResult:
    """
    Run the Intent-Gated Sufficiency Layer (read-only diagnostic).

    Flow (plan §4):
    1. Intent Classifier (non-LLM) → mandatory axes
    2. Parallel sufficiency signals: semantic, rule, structural
    3. Veto resolution (AND-logic)
    4. Final verdict + deciding_factor

    Does NOT: modify context, retrieval, ranking, prompts, or generation.
    """
    intent_result = classify_intent(query)

    # Parallel signals (deterministic; no LLM)
    semantic = compute_semantic_signal(query, context_artifact, embedder)
    rule = compute_rule_signal(query, context_artifact)
    structural = compute_structural_signal(context_artifact)

    signals = {
        "semantic": semantic,
        "rule": rule,
        "structural": structural,
    }

    return resolve_veto(intent_result, signals)


__all__ = ["run_sufficiency"]
