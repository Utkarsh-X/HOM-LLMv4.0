"""Synthesis profile for context-stage budget modulation (query-agnostic)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable

from homllm.retrieval.interfaces import Candidate


@dataclass(frozen=True)
class ContextSynthesisProfile:
    """Signals estimating whether context should bias toward multi-block coverage."""

    synthesis_score: float
    concept_density: float
    file_dispersion: float
    semantic_entropy: float
    retrieval_disagreement: float


def compute_context_synthesis_profile(
    query: str,
    candidates: Iterable[Candidate],
    semantic_scores: dict[str, float],
) -> ContextSynthesisProfile:
    """
    Continuous, query-agnostic synthesis score for context assembly.

    Uses only:
    - Concept density from generic tokenization (no keywords/heuristics)
    - File dispersion across candidates
    - Entropy of semantic scores (normalized)
    - Disagreement between BM25 and vector rankings (normalized)
    """
    cand_list = list(candidates)
    concepts = [c.lower() for c in extract_query_concepts(query)]

    # 1) Concept density (normalized by K=8)
    K = 8.0
    concept_density = min(len(concepts) / K, 1.0)

    # Consider only top_k candidates for dispersion/disagreement
    top_k = min(50, len(cand_list))
    top_candidates = cand_list[:top_k]

    # 2) File dispersion: distinct_files / top_k
    files = [c.file for c in top_candidates if c.file]
    file_dispersion = (len(set(files)) / max(top_k, 1)) if top_k > 0 else 0.0

    # 3) Semantic entropy from scores on provided candidates (normalized)
    semantic_entropy = _normalized_entropy(
        [semantic_scores.get(c.doc_id, 0.0) for c in top_candidates]
    )

    # 4) Retrieval disagreement as inverse correlation between bm25 and vector ranks
    retrieval_disagreement = _bm25_vector_disagreement(top_candidates)

    # Smooth weighted blend (renormalize if any component missing)
    components: list[tuple[float | None, float]] = [
        (concept_density, 0.30),
        (file_dispersion, 0.25),
        (semantic_entropy, 0.25),
        (retrieval_disagreement, 0.20),
    ]
    available = [(v, w) for v, w in components if v is not None]
    weight_sum = sum(w for _, w in available)
    if weight_sum <= 0:
        synthesis_score = 0.0
    else:
        synthesis_score = sum((w / weight_sum) * _clamp01(float(v)) for v, w in available)

    return ContextSynthesisProfile(
        synthesis_score=_clamp01(synthesis_score),
        concept_density=_clamp01(concept_density),
        file_dispersion=_clamp01(file_dispersion),
        semantic_entropy=_clamp01(semantic_entropy),
        retrieval_disagreement=_clamp01(retrieval_disagreement),
    )


def extract_query_concepts(query: str) -> list[str]:
    """Generic, query-agnostic concept extraction (no keyword rules)."""
    tokens = re.findall(r"\b[A-Za-z0-9_]+\b", query)
    # Keep short, high-signal identifiers; drop basic English stopwords.
    stopwords = {
        "what", "when", "where", "which", "who", "whom", "why", "how",
        "does", "do", "did", "is", "are", "was", "were", "be", "been",
        "the", "a", "an", "and", "or", "but", "if", "then", "than",
        "this", "that", "these", "those", "with", "without", "about",
        "into", "from", "to", "of", "for", "in", "on", "at", "by",
        "all", "any", "each", "every", "some", "most", "many", "few",
    }
    concepts: list[str] = []
    seen = set()
    for token in tokens:
        if len(token) < 2:
            continue
        t = token.lower()
        if t in stopwords:
            continue
        if t not in seen:
            seen.add(t)
            concepts.append(token)
    return concepts


def _normalized_entropy(values: list[float]) -> float:
    positives = [v for v in values if v > 0]
    if len(positives) <= 1:
        return 0.0
    total = sum(positives)
    if total <= 0:
        return 0.0
    probs = [v / total for v in positives]
    entropy = -sum(p * math.log(p) for p in probs if p > 0)
    max_entropy = math.log(len(probs))
    return entropy / max_entropy if max_entropy > 0 else 0.0


def _bm25_vector_disagreement(candidates: list[Candidate]) -> float:
    bm25_rank = _rank_map(candidates, key="bm25_score")
    vector_rank = _rank_map(candidates, key="vector_score")
    common = set(bm25_rank) & set(vector_rank)
    if len(common) < 2:
        return 0.0
    # Spearman distance normalized to [0,1]
    n = len(common)
    sum_sq = 0.0
    for doc_id in common:
        d = bm25_rank[doc_id] - vector_rank[doc_id]
        sum_sq += d * d
    corr = 1.0 - (6.0 * sum_sq) / (n * (n * n - 1))
    return _clamp01(1.0 - corr)


def _rank_map(candidates: list[Candidate], key: str, top_k: int = 50) -> dict[str, int]:
    scored = [
        (c.doc_id, getattr(c, key, 0.0))
        for c in candidates
        if getattr(c, key, 0.0) > 0
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return {doc_id: idx for idx, (doc_id, _) in enumerate(scored[:top_k], start=1)}


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value

