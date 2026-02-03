"""
Cross-Run Instability — Signal modules (spec § Signal Classes).

All read-only. No LLM calls. Deterministic statistics only.
"""

from homllm.instability.signals.answer_structure import answer_structure_variance
from homllm.instability.signals.embedding_consistency import embedding_consistency
from homllm.instability.signals.failure_frequency import failure_frequency
from homllm.instability.signals.metadata_variance import metadata_variance
from homllm.instability.signals.retrieval_overlap import retrieval_overlap_instability

# Re-export for callers that need RunRecord / PrimaryLabelType
from homllm.instability.interfaces import PrimaryLabelType, RunRecord

__all__ = [
    "answer_structure_variance",
    "embedding_consistency",
    "failure_frequency",
    "metadata_variance",
    "retrieval_overlap_instability",
]
