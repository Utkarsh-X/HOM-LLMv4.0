"""
Context Quality Evaluation Kernel.

Deterministic, language-agnostic, threshold-free quality metrics
for the HOM-LLM RAG pipeline.

Metrics:
    M1  Semantic Strength         mean cross-encoder score of context blocks
    M2  Query Term Recall          fraction of query terms found in context
    M3  File Entropy               normalized Shannon entropy of file distribution
    M4  Content Overlap            mean pairwise Jaccard similarity
    M5  Score Separation           coefficient of variation of final scores
    M6  Reranker Influence         reranker variance share of final scores
    M7  Budget Utilization         used_tokens / token_budget
"""

from homllm.quality.schema import MetricRecord
from homllm.quality.kernel import ContextQualityKernel
from homllm.quality.percentile import PercentileWindow

__all__ = [
    "MetricRecord",
    "ContextQualityKernel",
    "PercentileWindow",
]
