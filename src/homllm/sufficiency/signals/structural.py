"""
Structural Coverage Signal (plan §5.4).

Code-aware: symbol presence, block count, distinct components.
Hard veto when mandatory and failed. No LLM. Tree-sitter optional (not required).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homllm.sufficiency.interfaces import LabelType, SignalResult

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact


def compute_structural_signal(
    context_artifact: "ContextArtifact",
) -> SignalResult:
    """
    Structural coverage: code blocks, symbols, distinct files.
    Deterministic. Authority: hard veto when mandatory and failed (plan §5.4).
    """
    if not context_artifact.blocks:
        return SignalResult(score=0.0, label="INSUFFICIENT")

    blocks = context_artifact.blocks
    n_blocks = len(blocks)
    has_symbols = sum(1 for b in blocks if (b.symbol_name or b.symbol_id)) > 0
    distinct_files = len(set(b.file for b in blocks))
    code_like_extensions = {".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".h"}
    code_blocks = sum(
        1 for b in blocks
        if any(b.file.endswith(ext) for ext in code_like_extensions)
    )

    # Score: combination of presence of symbols, multiple blocks, multiple components
    score = 0.0
    if n_blocks >= 1:
        score += 0.3
    if n_blocks >= 2:
        score += 0.2
    if has_symbols:
        score += 0.3
    if distinct_files >= 1:
        score += 0.1
    if distinct_files >= 2:
        score += 0.1
    if code_blocks >= 1:
        score += 0.2
    score = max(0.0, min(1.0, score))

    # Structural insufficiency → hard veto when mandatory (handled in veto resolution)
    label: LabelType = "SUFFICIENT" if score >= 0.5 else "INSUFFICIENT"
    return SignalResult(score=score, label=label)
