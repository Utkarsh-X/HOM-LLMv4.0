"""
Core metric computation functions.

Each function is pure, deterministic, and language-agnostic.
No thresholds, no side effects, no LLM calls.

Metric functions accept raw data and return a single float.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Sequence

# ============================================================================
# STOPWORDS — language-agnostic function words for M2 (Query Term Recall)
# ============================================================================

_STOPWORDS: frozenset[str] = frozenset({
    "the", "is", "a", "of", "in", "to", "for", "and", "or", "not", "with",
    "on", "at", "by", "from", "as", "it", "this", "that", "an", "be", "are",
    "was", "were", "been", "do", "does", "did", "has", "have", "had", "will",
    "would", "can", "could", "should", "may", "might", "i", "me", "my", "we",
    "you", "your", "he", "she", "they", "them", "its",
})

_TOKEN_SPLIT = re.compile(r"[^a-z0-9_]+")


def _tokenize(text: str) -> set[str]:
    """Lowercase whitespace+punctuation split, unique terms, stopwords removed."""
    tokens = _TOKEN_SPLIT.split(text.lower())
    return {t for t in tokens if t and len(t) > 1 and t not in _STOPWORDS}


# ============================================================================
# M1 — Semantic Strength
# ============================================================================

def semantic_strength(
    rerank_scores: Sequence[float],
) -> float:
    """
    Mean cross-encoder score of context blocks.

    Args:
        rerank_scores: Cross-encoder scores for each block in the final context.
                       Obtained by joining ContextArtifact.blocks → DebugTrace.rerank_score.

    Returns:
        Arithmetic mean. 0.0 if no scores.
    """
    if not rerank_scores:
        return 0.0
    return sum(rerank_scores) / len(rerank_scores)


# ============================================================================
# M2 — Query Term Recall
# ============================================================================

def query_term_recall(
    query: str,
    block_contents: Sequence[str],
) -> float:
    """
    Fraction of query terms found in at least one context block.

    Args:
        query: Raw query text.
        block_contents: Content of each block in the final context.

    Returns:
        Float in [0.0, 1.0]. 0.0 if query has no meaningful terms.
    """
    query_terms = _tokenize(query)
    if not query_terms:
        return 0.0

    # Build union of all block terms
    context_terms: set[str] = set()
    for content in block_contents:
        context_terms.update(_tokenize(content))

    hits = query_terms & context_terms
    return len(hits) / len(query_terms)


# ============================================================================
# M3 — File Entropy
# ============================================================================

def file_entropy(
    block_files: Sequence[str],
) -> float:
    """
    Normalized Shannon entropy of file distribution in context blocks.

    Args:
        block_files: File path for each block in the final context.

    Returns:
        Float in [0.0, 1.0]. 0.0 if single file or no blocks.
    """
    if not block_files:
        return 0.0

    k = len(block_files)
    counts = Counter(block_files)
    unique = len(counts)

    if unique <= 1:
        return 0.0

    # Shannon entropy
    h = 0.0
    for count in counts.values():
        p = count / k
        if p > 0:
            h -= p * math.log(p)

    # Normalize by log(unique_files)
    h_max = math.log(unique)
    if h_max == 0:
        return 0.0

    return h / h_max


# ============================================================================
# M4 — Content Overlap
# ============================================================================

def content_overlap(
    block_contents: Sequence[str],
) -> float:
    """
    Mean pairwise Jaccard similarity among context blocks.

    Args:
        block_contents: Content of each block in the final context.

    Returns:
        Float in [0.0, 1.0]. 0.0 if 0 or 1 block.
    """
    k = len(block_contents)
    if k <= 1:
        return 0.0

    # Tokenize all blocks
    token_sets = [_tokenize(c) for c in block_contents]

    # Mean pairwise Jaccard
    total_jaccard = 0.0
    pair_count = 0

    for i in range(k):
        for j in range(i + 1, k):
            a, b = token_sets[i], token_sets[j]
            union = a | b
            if not union:
                # Both blocks are empty or only stopwords
                continue
            intersection = a & b
            total_jaccard += len(intersection) / len(union)
            pair_count += 1

    if pair_count == 0:
        return 0.0

    return total_jaccard / pair_count


# ============================================================================
# M5 — Score Separation
# ============================================================================

def score_separation(
    final_scores: Sequence[float],
) -> float:
    """
    Coefficient of variation of final ranking scores.

    Args:
        final_scores: Final scores for ALL ranked candidates (not just selected).

    Returns:
        CV (σ/μ). 0.0 if mean is near-zero or no scores.
    """
    if not final_scores:
        return 0.0

    n = len(final_scores)
    mu = sum(final_scores) / n

    if abs(mu) < 1e-10:
        return 0.0

    variance = sum((s - mu) ** 2 for s in final_scores) / n
    sigma = math.sqrt(variance)

    return sigma / abs(mu)


# ============================================================================
# M6 — Reranker Influence
# ============================================================================

def reranker_influence(
    final_scores: Sequence[float],
    rerank_scores: Sequence[float],
    rerank_alpha: float,
) -> float:
    """
    Reranker variance share of final scores using Stage-2 delta geometry.

    Measures: Var(α × rerank_delta) / Var(final_score)
    where rerank_delta = rerank_score - mean(rerank_scores)

    This matches the ranking pipeline geometry:
        final_score = base_score + α × (rerank_score − mean_rerank) + γ × struct_bonus

    Args:
        final_scores: Final combined scores for all candidates on the full ranked surface.
        rerank_scores: Raw reranker scores for all candidates (0.0 for non-reranked).
        rerank_alpha: Alpha coefficient from RankConfig.rerank_alpha (NOT w_rerank).

    Returns:
        Float in [0.0, 1.0]. 0.0 if final score variance is zero or no rerank scores.
    """
    if not final_scores or not rerank_scores:
        return 0.0

    n = len(final_scores)
    if n != len(rerank_scores):
        return 0.0

    # Variance of final scores
    mu_final = sum(final_scores) / n
    var_final = sum((s - mu_final) ** 2 for s in final_scores) / n

    if var_final < 1e-15:
        return 0.0

    # Compute rerank delta: rerank_score - mean(rerank_scores)
    # Only non-zero rerank scores contribute to the mean (matching pipeline logic).
    rerank_nonzero = [s for s in rerank_scores if s != 0.0]
    rerank_mean = (sum(rerank_nonzero) / len(rerank_nonzero)) if rerank_nonzero else 0.0

    # Alpha-weighted rerank deltas (0.0 for candidates not reranked)
    alpha_deltas = []
    for rs in rerank_scores:
        if rs != 0.0:
            alpha_deltas.append(rerank_alpha * (rs - rerank_mean))
        else:
            alpha_deltas.append(0.0)

    # Variance of alpha-weighted deltas
    mu_alpha_delta = sum(alpha_deltas) / n
    var_alpha_delta = sum((d - mu_alpha_delta) ** 2 for d in alpha_deltas) / n

    return min(1.0, var_alpha_delta / var_final)


# ============================================================================
# M7 — Budget Utilization
# ============================================================================

def budget_utilization(
    used_tokens: int,
    token_budget: int,
) -> float:
    """
    Token budget usage ratio.

    Args:
        used_tokens: Actual tokens in final context.
        token_budget: Allocated token budget.

    Returns:
        Float in [0.0, 1.0+]. 0.0 if budget is zero.
    """
    if token_budget <= 0:
        return 0.0

    return used_tokens / token_budget
