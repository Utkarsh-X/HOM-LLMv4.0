"""
Level-1 Action Rules

Pure rule evaluators for structural diagnostics.
Each rule is a stateless function: (IntraBlockDiagnostic) -> list[ProposedAction]

CONSTRAINTS (ABSOLUTE):
- Pure functions only
- No side effects
- No cross-rule dependencies
- No conflict resolution (that's resolver's job)
- No LLM or ML
- Deterministic
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homllm.intelligence.actions.level1.plan import (
    ActionType,
    ProposedAction,
)

if TYPE_CHECKING:
    from homllm.intelligence.diagnostics.inspect_context import IntraBlockDiagnostic


# =============================================================================
# RULE REGISTRY
# =============================================================================

# All rules are registered here for the engine to collect
_RULE_REGISTRY: list[tuple[str, callable]] = []


def rule(name: str):
    """Decorator to register a rule function."""
    def decorator(fn):
        _RULE_REGISTRY.append((name, fn))
        return fn
    return decorator


def get_all_rules() -> list[tuple[str, callable]]:
    """Return all registered rules."""
    return list(_RULE_REGISTRY)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_evidence(block: IntraBlockDiagnostic, **extra) -> tuple[tuple[str, any], ...]:
    """Create frozen evidence tuple from diagnostic."""
    base = {
        "block_id": block.block_id,
        "tokens": block.tokens,
        "signal_ratio": block.signal_ratio,
        "noise_ratio": block.noise_ratio,
    }
    base.update(extra)
    return tuple(sorted(base.items()))


# =============================================================================
# NOISE RULES
# =============================================================================

@rule("noise_drop")
def rule_noise_drop(block: IntraBlockDiagnostic) -> list[ProposedAction]:
    """
    DROP blocks with very high noise ratio.
    
    Threshold: noise_ratio > 0.45
    Rationale: Block is mostly noise, provides little signal to LLM.
    """
    if block.noise_ratio > 0.45:
        return [ProposedAction(
            block_id=block.block_id,
            action_type=ActionType.DROP,
            confidence=0.8,
            reason=f"High noise ratio ({block.noise_ratio:.2f} > 0.45)",
            originating_rule="noise_drop",
            evidence=make_evidence(block),
        )]
    return []


@rule("logging_compact")
def rule_logging_compact(block: IntraBlockDiagnostic) -> list[ProposedAction]:
    """
    COMPACT blocks with excessive logging.
    
    Threshold: logging_pct > 20%
    Rationale: Logging is noise in context, can be stripped.
    """
    logging_pct = block.token_breakdown.logging_pct
    if logging_pct > 20.0:
        return [ProposedAction(
            block_id=block.block_id,
            action_type=ActionType.COMPACT,
            confidence=0.7,
            reason=f"Excessive logging ({logging_pct:.1f}% > 20%)",
            originating_rule="logging_compact",
            evidence=make_evidence(block, logging_pct=logging_pct),
        )]
    return []


@rule("docstring_compact")
def rule_docstring_compact(block: IntraBlockDiagnostic) -> list[ProposedAction]:
    """
    COMPACT blocks with excessive docstrings.
    
    Threshold: docstrings_pct > 30%
    Rationale: Docstrings are valuable but can dominate token budget.
    """
    docstrings_pct = block.token_breakdown.docstrings_pct
    if docstrings_pct > 30.0:
        return [ProposedAction(
            block_id=block.block_id,
            action_type=ActionType.COMPACT,
            confidence=0.6,
            reason=f"Excessive docstrings ({docstrings_pct:.1f}% > 30%)",
            originating_rule="docstring_compact",
            evidence=make_evidence(block, docstrings_pct=docstrings_pct),
        )]
    return []


# =============================================================================
# REDUNDANCY RULES
# =============================================================================

@rule("redundancy_dedupe")
def rule_redundancy_dedupe(block: IntraBlockDiagnostic) -> list[ProposedAction]:
    """
    DEDUPE blocks with high boilerplate score.
    
    Threshold: boilerplate_score > 0.70
    Rationale: High boilerplate suggests repetitive patterns.
    """
    boilerplate = block.redundancy_hints.boilerplate_score
    if boilerplate > 0.70:
        return [ProposedAction(
            block_id=block.block_id,
            action_type=ActionType.DEDUPE,
            confidence=0.75,
            reason=f"High boilerplate ({boilerplate:.2f} > 0.70)",
            originating_rule="redundancy_dedupe",
            evidence=make_evidence(block, boilerplate_score=boilerplate),
        )]
    return []


# =============================================================================
# STRUCTURAL PRIORITY RULES
# =============================================================================

@rule("role_define_protect")
def rule_role_define_protect(block: IntraBlockDiagnostic) -> list[ProposedAction]:
    """
    PROTECT blocks that define key structures with low noise.
    
    Criteria: function_count > 0 AND noise_ratio < 0.2
    Rationale: Core definitions are critical for understanding.
    """
    struct = block.structural_payload
    is_definition = struct.function_count > 0 or struct.class_count > 0
    is_clean = block.noise_ratio < 0.2
    
    if is_definition and is_clean:
        return [ProposedAction(
            block_id=block.block_id,
            action_type=ActionType.PROTECT,
            confidence=0.9,
            reason="Core definition with low noise",
            originating_rule="role_define_protect",
            evidence=make_evidence(
                block,
                function_count=struct.function_count,
                class_count=struct.class_count,
            ),
        )]
    return []


@rule("role_implement_keep")
def rule_role_implement_keep(block: IntraBlockDiagnostic) -> list[ProposedAction]:
    """
    KEEP blocks that implement logic with reasonable signal.
    
    Criteria: function_count > 0 AND signal_ratio > 0.3
    Rationale: Implementation blocks with good signal should be retained.
    """
    struct = block.structural_payload
    has_functions = struct.function_count > 0 or struct.method_count > 0
    has_signal = block.signal_ratio > 0.3
    
    if has_functions and has_signal:
        return [ProposedAction(
            block_id=block.block_id,
            action_type=ActionType.KEEP,
            confidence=0.8,
            reason=f"Implementation with good signal ({block.signal_ratio:.2f})",
            originating_rule="role_implement_keep",
            evidence=make_evidence(
                block,
                function_count=struct.function_count,
                method_count=struct.method_count,
            ),
        )]
    return []


@rule("role_noise_downweight")
def rule_role_noise_downweight(block: IntraBlockDiagnostic) -> list[ProposedAction]:
    """
    DOWNWEIGHT blocks with moderate noise and low signal.
    
    Criteria: noise_ratio > 0.30 AND signal_ratio < 0.4
    Rationale: Not bad enough to drop, but should rank lower.
    """
    is_noisy = block.noise_ratio > 0.30
    low_signal = block.signal_ratio < 0.4
    
    if is_noisy and low_signal:
        return [ProposedAction(
            block_id=block.block_id,
            action_type=ActionType.DOWNWEIGHT,
            confidence=0.6,
            reason=f"Moderate noise ({block.noise_ratio:.2f}), low signal ({block.signal_ratio:.2f})",
            originating_rule="role_noise_downweight",
            evidence=make_evidence(block),
        )]
    return []


__all__ = [
    "get_all_rules",
    "ProposedAction",
]
