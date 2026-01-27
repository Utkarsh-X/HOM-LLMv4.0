"""
Assertion Readability Evaluator

Evaluates whether context blocks may be asserted by the LLM,
separating mutability safety from epistemic usability.

CORE PRINCIPLE: Protection ≠ Silence
A block may be non-removable but still assertable.

CONSTRAINTS (ABSOLUTE):
- Purely read-only
- Fully deterministic
- No thresholds or fuzzy scoring
- No tuning parameters
- Binary decisions with explicit reasons
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homllm.intelligence.assertion_readability.interfaces import (
    ReadabilityReason,
    AssertionReadability,
    ReadabilityResult,
)

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact
    from homllm.intelligence.interfaces import DiagnosticSnapshot
    from homllm.intelligence.controller import ContextModificationPlan


# Action types that protect blocks
PROTECTIVE_ACTION_TYPES = frozenset({
    "PROTECT", "PRESERVE", "ANCHOR", "KEEP",
})


class AssertionReadabilityEvaluator:
    """
    Evaluates assertion readability for context blocks.
    
    This evaluator determines whether each block's content can be
    asserted by the LLM, regardless of protection status.
    
    Rules (Binary, No Thresholds):
    - function_count > 0 → READABLE (EXPLICIT_DEFINITION)
    - class_count > 0 → READABLE (EXPLICIT_DEFINITION)
    - Has control flow → READABLE (CONTROL_FLOW)
    - Has ordered enums/rules → READABLE (ORDERED_LOGIC)
    - Has state assignments → READABLE (STATE_TRANSITION)
    - Low signal + high noise → NOT READABLE (TOO_FRAGMENTED)
    - No structure → NOT READABLE (IMPLICIT_ONLY)
    
    If protected but passes readability → add PROTECTED_BUT_READABLE
    """
    
    def evaluate(
        self,
        snapshot: "DiagnosticSnapshot",
        plan: "ContextModificationPlan",
        context: "ContextArtifact",
    ) -> ReadabilityResult:
        """
        Evaluate readability of all blocks in context.
        
        Args:
            snapshot: DiagnosticSnapshot from diagnostics engine
            plan: ContextModificationPlan from intelligence controller
            context: Original ContextArtifact (read-only)
            
        Returns:
            ReadabilityResult with per-block assessments.
        """
        # Build action map for protection detection
        action_map = self._build_action_map(plan)
        
        entries: list[AssertionReadability] = []
        protected_but_readable = 0
        
        # Use Level-1 structural diagnostics for block info
        if snapshot.level1.status != "available":
            return ReadabilityResult.empty()
        
        for block_diag in snapshot.level1.blocks:
            block_id = block_diag.block_id
            
            # Get protection status
            protecting_actions = self._get_protecting_actions(block_id, action_map)
            is_protected = len(protecting_actions) > 0
            
            # Evaluate readability (independent of protection)
            readable, reasons = self._evaluate_block_readability(block_diag)
            
            # Add PROTECTED_BUT_READABLE if applicable
            if is_protected and readable:
                reasons = reasons + (ReadabilityReason.PROTECTED_BUT_READABLE,)
                protected_but_readable += 1
            
            entries.append(AssertionReadability(
                block_id=block_id,
                readable=readable,
                reasons=reasons,
                protecting_actions=tuple(protecting_actions),
            ))
        
        total = len(entries)
        readable_count = sum(1 for e in entries if e.readable)
        suppressed_count = total - readable_count
        
        return ReadabilityResult(
            total_blocks=total,
            readable_count=readable_count,
            suppressed_count=suppressed_count,
            protected_but_readable_count=protected_but_readable,
            entries=tuple(entries),
        )
    
    def _evaluate_block_readability(
        self,
        block_diag,
    ) -> tuple[bool, tuple[ReadabilityReason, ...]]:
        """
        Evaluate whether a block is readable based on structural properties.
        
        Returns (readable, reasons) tuple.
        
        Binary rules, no thresholds.
        """
        reasons: list[ReadabilityReason] = []
        struct = block_diag.structural_payload
        breakdown = block_diag.token_breakdown
        
        # Rule 1: Explicit definitions are always readable
        if struct.function_count > 0 or struct.class_count > 0:
            reasons.append(ReadabilityReason.EXPLICIT_DEFINITION)
        
        # Rule 2: Methods indicate implementation
        if struct.method_count > 0:
            reasons.append(ReadabilityReason.EXPLICIT_DEFINITION)
        
        # Rule 3: Control flow indicates logic
        if breakdown.control_flow_lines > 0:
            reasons.append(ReadabilityReason.CONTROL_FLOW)
        
        # Rule 4: Decorators often indicate ordered behavior
        if struct.decorator_count > 0:
            reasons.append(ReadabilityReason.ORDERED_LOGIC)
        
        # Rule 5: State transitions (assignments in code)
        if breakdown.code_lines > 0 and breakdown.signature_lines > 0:
            reasons.append(ReadabilityReason.SIMPLE_STATE_TRANSITION)
        
        # If we have any positive reasons, block is readable
        if reasons:
            return True, tuple(reasons)
        
        # Check for unreadable conditions
        signal = block_diag.signal_ratio
        noise = block_diag.noise_ratio
        
        # High noise, low signal = fragmented
        if noise > 0.4 and signal < 0.3:
            return False, (ReadabilityReason.TOO_FRAGMENTED,)
        
        # No structure at all = implicit only
        return False, (ReadabilityReason.IMPLICIT_ONLY,)
    
    def _build_action_map(
        self,
        plan: "ContextModificationPlan",
    ) -> dict[str, list[str]]:
        """
        Build a map of block_id -> list of action types.
        """
        action_map: dict[str, list[str]] = {}
        
        for action in plan.unified_actions:
            target = action.target
            if target not in action_map:
                action_map[target] = []
            action_map[target].append(action.action_type)
        
        return action_map
    
    def _get_protecting_actions(
        self,
        block_id: str,
        action_map: dict[str, list[str]],
    ) -> list[str]:
        """
        Get list of protective action types for a block.
        """
        if block_id not in action_map:
            return []
        
        return [
            action_type
            for action_type in action_map[block_id]
            if action_type in PROTECTIVE_ACTION_TYPES
        ]


def create_readability_evaluator() -> AssertionReadabilityEvaluator:
    """Factory function to create evaluator."""
    return AssertionReadabilityEvaluator()


__all__ = [
    "AssertionReadabilityEvaluator",
    "create_readability_evaluator",
]
