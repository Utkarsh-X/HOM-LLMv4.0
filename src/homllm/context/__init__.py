"""Context Assembly layer - Phase 4: Token-budgeted context curation."""

from homllm.context.interfaces import (
    ContextArtifact,
    ContextBlock,
    ScoredBlock,
    AllocatedBlock,
    BudgetConfig,
    ContextConfig,
    BlockScorer,
    BudgetManager,
    Stitcher,
)
from homllm.context.pipeline import ContextPipeline
from homllm.context.diff import (
    ContextDiff,
    DiffEntry,
    ConflictRecord,
    DiffBuilder,
)
from homllm.context.applier import (
    ContextApplier,
    ApplierConfig,
    ApplierResult,
    create_context_applier,
)

__all__ = [
    "ContextArtifact",
    "ContextBlock",
    "ScoredBlock",
    "AllocatedBlock",
    "BudgetConfig",
    "ContextConfig",
    "BlockScorer",
    "BudgetManager",
    "Stitcher",
    "ContextPipeline",
    # Diff types
    "ContextDiff",
    "DiffEntry",
    "ConflictRecord",
    "DiffBuilder",
    # Applier
    "ContextApplier",
    "ApplierConfig",
    "ApplierResult",
    "create_context_applier",
]

