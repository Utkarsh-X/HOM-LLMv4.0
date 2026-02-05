"""Deterministic entity confidence scoring for entity-centric indexing.

This module implements config-driven confidence scoring for entities.
All weights come from configuration, not hardcoded values.

Scoring Rules:
- Public name bonus: Entity name has no leading underscore
- Docstring bonus: Entity has an associated docstring
- Exported bonus: Entity is in __all__ or re-exported
- Type annotation bonus: Entity has type hints

The score is capped at the configured maximum (default 1.0).
"""

from dataclasses import dataclass
from typing import Protocol

from homllm.common.config import EntityConfidenceConfig


@dataclass(frozen=True)
class ConfidenceInputs:
    """
    Input signals for confidence scoring.
    
    These are extracted during entity extraction and passed
    to the scorer for deterministic scoring.
    """
    
    name: str                    # Entity name (for public name check)
    has_docstring: bool          # Whether entity has a docstring
    is_exported: bool            # Whether in __all__ or re-exported
    has_type_annotation: bool    # Whether type hints are present


def compute_entity_confidence(
    inputs: ConfidenceInputs,
    config: EntityConfidenceConfig,
) -> float:
    """
    Compute deterministic confidence score for an entity.
    
    This scoring is fully deterministic and config-driven:
    - No randomness
    - No ML/LLM inference
    - All weights from config, not hardcoded
    
    Args:
        inputs: Signal inputs for scoring
        config: Confidence scoring configuration with weights
        
    Returns:
        Confidence score between 0.0 and config.cap_at (default 1.0)
        
    Example:
        >>> inputs = ConfidenceInputs(
        ...     name="process_data",
        ...     has_docstring=True,
        ...     is_exported=True,
        ...     has_type_annotation=True
        ... )
        >>> config = EntityConfidenceConfig()  # default weights
        >>> score = compute_entity_confidence(inputs, config)
        >>> score  # 0.3 + 0.4 + 0.2 + 0.1 = 1.0 (capped at 1.0)
        1.0
    """
    score = 0.0
    
    # Public name bonus: no leading underscore
    if not inputs.name.startswith("_"):
        score += config.public_name_bonus
    
    # Docstring bonus
    if inputs.has_docstring:
        score += config.docstring_bonus
    
    # Exported bonus (in __all__ or re-exported)
    if inputs.is_exported:
        score += config.exported_bonus
    
    # Type annotation bonus
    if inputs.has_type_annotation:
        score += config.type_annotated_bonus
    
    # Cap at configured maximum
    return min(score, config.cap_at)


def is_public_name(name: str) -> bool:
    """
    Check if a name is public (no leading underscore).
    
    Args:
        name: Entity name
        
    Returns:
        True if name doesn't start with underscore
    """
    return not name.startswith("_")


def compute_docstring_hash(docstring: str) -> str:
    """
    Compute stable hash of docstring for deduplication.
    
    Args:
        docstring: The docstring content
        
    Returns:
        SHA-256 hash truncated to 16 characters
    """
    import hashlib
    return hashlib.sha256(docstring.encode()).hexdigest()[:16]
