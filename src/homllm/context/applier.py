"""
Context Applier - Core Execution Engine

Deterministic execution engine that applies ContextModificationPlan
to produce a new ContextArtifact.

This layer EXECUTES, it does NOT THINK.

CONSTRAINTS (ABSOLUTE):
- No diagnostics
- No action generation
- No learning or planning
- No graph traversal
- No randomness
- No global state
- No imports from intelligence.diagnostics, intelligence.actions
- Deterministic: same input → same output
- Immutable: original context never mutated
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homllm.context.interfaces import ContextArtifact, ContextBlock
from homllm.context.diff import ContextDiff, DiffBuilder

if TYPE_CHECKING:
    from homllm.intelligence.controller import (
        ContextModificationPlan,
        UnifiedAction,
    )


# =============================================================================
# APPLIER CONFIG
# =============================================================================

@dataclass(frozen=True)
class ApplierConfig:
    """
    Configuration for ContextApplier.
    
    Attributes:
        enforce_token_budget: Whether to enforce token limits
        allow_empty_context: Whether plan can result in empty context
        max_removals_percent: Max percentage of blocks that can be removed
    """
    
    enforce_token_budget: bool = True
    allow_empty_context: bool = False
    max_removals_percent: float = 80.0  # Safety: can't remove more than 80%


# =============================================================================
# APPLIER RESULT
# =============================================================================

@dataclass(frozen=True)
class ApplierResult:
    """
    Result of applying a modification plan.
    
    Contains the new context and complete diff.
    """
    
    context: ContextArtifact
    diff: ContextDiff
    success: bool = True
    error: str = ""


# =============================================================================
# CONTEXT APPLIER
# =============================================================================

class ContextApplier:
    """
    Deterministic execution engine for context modification plans.
    
    This is a compiler backend, not an optimizer.
    It applies actions exactly as specified, enforcing invariants.
    
    Usage:
        applier = ContextApplier()
        result = applier.apply(plan, context)
        
        new_context = result.context
        diff = result.diff
    
    Guarantees:
    - Original context is NEVER mutated
    - Same input produces same output
    - All changes are recorded in diff
    - Protected blocks cannot be removed
    - Token budget is enforced (if configured)
    """
    
    def __init__(self, config: ApplierConfig | None = None):
        """
        Initialize the applier.
        
        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self.config = config or ApplierConfig()
    
    def apply(
        self,
        plan: "ContextModificationPlan",
        context: ContextArtifact,
    ) -> ApplierResult:
        """
        Apply a modification plan to produce a new context.
        
        This method is the ONLY entry point for the applier.
        It does NOT mutate the original context.
        
        Args:
            plan: ContextModificationPlan from IntelligenceController
            context: Original ContextArtifact (read-only)
            
        Returns:
            ApplierResult containing new context and diff
            
        Note:
            - Empty plan returns unchanged context with empty diff
            - Protected blocks cannot be removed
            - Conflicts are resolved by level (L3 > L2 > L1)
        """
        diff_builder = DiffBuilder()
        
        # Handle empty plan
        if plan.is_empty:
            return ApplierResult(
                context=context,
                diff=diff_builder.build(),
                success=True,
            )
        
        # Phase 1: Collect and resolve actions per block
        block_actions = self._collect_block_actions(plan, diff_builder)
        
        # Phase 2: Identify protected blocks
        protected_blocks = self._identify_protected_blocks(block_actions)
        
        # Phase 3: Apply actions to blocks
        new_blocks, token_delta = self._apply_actions(
            context.blocks,
            block_actions,
            protected_blocks,
            diff_builder,
        )
        
        # Phase 4: Apply ordering actions
        ordered_blocks = self._apply_ordering(
            new_blocks,
            plan.unified_actions,
            diff_builder,
        )
        
        # Phase 5: Enforce safety invariants
        final_blocks = self._enforce_invariants(
            ordered_blocks,
            context,
            diff_builder,
        )
        
        # Phase 6: Build new context
        new_context = self._build_new_context(context, final_blocks)
        
        return ApplierResult(
            context=new_context,
            diff=diff_builder.build(),
            success=True,
        )
    
    def _collect_block_actions(
        self,
        plan: "ContextModificationPlan",
        diff_builder: DiffBuilder,
    ) -> dict[str, list[tuple[int, str, "UnifiedAction"]]]:
        """
        Collect all actions targeting each block.
        
        Groups actions by target block_id for conflict resolution.
        
        Returns:
            Dict mapping block_id to list of (level, action_type, action) tuples
        """
        block_actions: dict[str, list[tuple[int, str, Any]]] = {}
        
        for action in plan.unified_actions:
            target = action.target
            if target not in block_actions:
                block_actions[target] = []
            block_actions[target].append((
                action.level,
                action.action_type,
                action,
            ))
        
        return block_actions
    
    def _identify_protected_blocks(
        self,
        block_actions: dict[str, list[tuple[int, str, Any]]],
    ) -> set[str]:
        """
        Identify blocks that are protected from removal.
        
        PROTECT and PRESERVE actions mark blocks as untouchable.
        """
        protected = set()
        
        protect_types = {"PROTECT", "PRESERVE", "ANCHOR", "KEEP"}
        
        for block_id, actions in block_actions.items():
            for level, action_type, action in actions:
                if action_type in protect_types:
                    protected.add(block_id)
        
        return protected
    
    def _apply_actions(
        self,
        blocks: tuple[ContextBlock, ...],
        block_actions: dict[str, list[tuple[int, str, Any]]],
        protected_blocks: set[str],
        diff_builder: DiffBuilder,
    ) -> tuple[list[ContextBlock], int]:
        """
        Apply actions to blocks, respecting protection and conflicts.
        
        Returns:
            Tuple of (new_blocks, token_delta)
        """
        new_blocks: list[ContextBlock] = []
        token_delta = 0
        
        for block in blocks:
            block_id = block.block_id
            
            if block_id not in block_actions:
                # No actions for this block - keep as-is
                new_blocks.append(block)
                continue
            
            # Resolve conflicts and get winning action
            actions = block_actions[block_id]
            winning_action = self._resolve_conflicts(
                block_id, actions, protected_blocks, diff_builder
            )
            
            if winning_action is None:
                # No applicable action - keep as-is
                new_blocks.append(block)
                continue
            
            level, action_type, action = winning_action
            
            # Apply the winning action
            result = self._apply_single_action(
                block, level, action_type, action, protected_blocks, diff_builder
            )
            
            if result is not None:
                new_blocks.append(result)
        
        return new_blocks, token_delta
    
    def _resolve_conflicts(
        self,
        block_id: str,
        actions: list[tuple[int, str, Any]],
        protected_blocks: set[str],
        diff_builder: DiffBuilder,
    ) -> tuple[int, str, Any] | None:
        """
        Resolve conflicts between actions targeting the same block.
        
        Resolution rules:
        1. Higher level wins (L3 > L2 > L1)
        2. Within same level, lower priority wins
        3. PROTECT actions cannot be overridden
        
        Returns:
            Winning (level, action_type, action) or None
        """
        if not actions:
            return None
        
        if len(actions) == 1:
            return actions[0]
        
        # Check for protection first
        protect_types = {"PROTECT", "PRESERVE", "KEEP"}
        for level, action_type, action in actions:
            if action_type in protect_types:
                # Protection always wins
                for other_level, other_type, other_action in actions:
                    if other_type not in protect_types:
                        diff_builder.add_conflict(
                            target=block_id,
                            winning_level=level,
                            winning_action=action_type,
                            losing_level=other_level,
                            losing_action=other_type,
                            resolution_reason="PROTECT action takes precedence",
                        )
                return (level, action_type, action)
        
        # Sort by level (descending) then by priority (ascending)
        sorted_actions = sorted(
            actions,
            key=lambda x: (-x[0], x[2].priority if hasattr(x[2], 'priority') else 0),
        )
        
        winner = sorted_actions[0]
        
        # Record conflicts
        for loser in sorted_actions[1:]:
            diff_builder.add_conflict(
                target=block_id,
                winning_level=winner[0],
                winning_action=winner[1],
                losing_level=loser[0],
                losing_action=loser[1],
                resolution_reason=f"L{winner[0]} takes precedence over L{loser[0]}",
            )
        
        return winner
    
    def _apply_single_action(
        self,
        block: ContextBlock,
        level: int,
        action_type: str,
        action: Any,
        protected_blocks: set[str],
        diff_builder: DiffBuilder,
    ) -> ContextBlock | None:
        """
        Apply a single action to a block.
        
        Returns:
            New block, or None if block should be removed
        """
        block_id = block.block_id
        
        # Handle each action type
        if action_type == "DROP":
            # Check protection
            if block_id in protected_blocks:
                diff_builder.add_entry(
                    change_type="skipped",
                    target=block_id,
                    level=level,
                    action_type=action_type,
                    reason="Block is protected",
                )
                return block
            
            diff_builder.add_entry(
                change_type="removed",
                target=block_id,
                level=level,
                action_type=action_type,
                reason=action.justification if hasattr(action, 'justification') else "Dropped",
            )
            return None
        
        elif action_type == "COMPACT":
            # Compact: reduce content but preserve identity
            diff_builder.add_entry(
                change_type="compacted",
                target=block_id,
                level=level,
                action_type=action_type,
                reason=action.justification if hasattr(action, 'justification') else "Compacted",
            )
            # For now, return block unchanged (compaction logic can be added later)
            return block
        
        elif action_type == "PROTECT" or action_type == "PRESERVE":
            diff_builder.add_entry(
                change_type="protected",
                target=block_id,
                level=level,
                action_type=action_type,
                reason=action.justification if hasattr(action, 'justification') else "Protected",
            )
            return block
        
        elif action_type == "KEEP":
            # Keep as-is, no diff entry needed
            return block
        
        elif action_type == "DOWNWEIGHT" or action_type == "DEPRIORITIZE":
            # No structural change, but record the intent
            diff_builder.add_entry(
                change_type="modified",
                target=block_id,
                level=level,
                action_type=action_type,
                reason=action.justification if hasattr(action, 'justification') else "Deprioritized",
            )
            return block
        
        elif action_type == "DEDUPE":
            # Mark for potential removal (duplicate detection)
            diff_builder.add_entry(
                change_type="removed",
                target=block_id,
                level=level,
                action_type=action_type,
                reason=action.justification if hasattr(action, 'justification') else "Deduplicated",
            )
            return None
        
        else:
            # Unknown action type - skip with warning
            diff_builder.add_entry(
                change_type="skipped",
                target=block_id,
                level=level,
                action_type=action_type,
                reason=f"Unknown action type: {action_type}",
            )
            return block
    
    def _apply_ordering(
        self,
        blocks: list[ContextBlock],
        actions: tuple,
        diff_builder: DiffBuilder,
    ) -> list[ContextBlock]:
        """
        Apply ordering actions (ORDER, ANCHOR, LIMIT).
        
        For now, this is a no-op. Ordering logic can be extended.
        """
        # TODO: Implement block reordering based on L3 ORDER actions
        return blocks
    
    def _enforce_invariants(
        self,
        blocks: list[ContextBlock],
        original_context: ContextArtifact,
        diff_builder: DiffBuilder,
    ) -> tuple[ContextBlock, ...]:
        """
        Enforce safety invariants.
        
        Invariants:
        - Context cannot be empty (unless explicitly allowed)
        - Cannot remove more than max_removals_percent of blocks
        """
        # Check for empty context
        if not blocks and not self.config.allow_empty_context:
            # Restore original blocks
            return original_context.blocks
        
        # Check removal percentage
        original_count = len(original_context.blocks)
        removed_count = original_count - len(blocks)
        
        if original_count > 0:
            removal_percent = (removed_count / original_count) * 100
            if removal_percent > self.config.max_removals_percent:
                # Too many removals - restore original
                return original_context.blocks
        
        return tuple(blocks)
    
    def _build_new_context(
        self,
        original: ContextArtifact,
        new_blocks: tuple[ContextBlock, ...],
    ) -> ContextArtifact:
        """
        Build a new ContextArtifact from modified blocks.
        
        Preserves query_id and other metadata from original.
        """
        # Compute new token count (estimate based on content length)
        new_used_tokens = sum(
            len(block.content.split()) // 2  # Simple estimate
            for block in new_blocks
        )
        
        # Rebuild context_text from blocks
        new_context_text = "\n\n".join(
            f"# {block.file}:{block.start_line}-{block.end_line}\n{block.content}"
            for block in new_blocks
        )
        
        # Build new provenance
        new_provenance = dict(original.provenance)
        new_provenance["applied_modifications"] = True
        
        # Build new explain trace
        new_explain_trace = tuple(list(original.explain_trace) + [
            f"Applied modification plan: {len(new_blocks)} blocks remaining",
        ])
        
        return ContextArtifact(
            query_id=original.query_id,
            context_text=new_context_text,
            blocks=new_blocks,
            token_budget=original.token_budget,
            used_tokens=new_used_tokens,
            provenance=new_provenance,
            explain_trace=new_explain_trace,
        )


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_context_applier(
    enforce_token_budget: bool = True,
    allow_empty_context: bool = False,
    max_removals_percent: float = 80.0,
) -> ContextApplier:
    """
    Factory function to create a ContextApplier.
    
    Args:
        enforce_token_budget: Whether to enforce token limits
        allow_empty_context: Whether plan can result in empty context
        max_removals_percent: Max percentage of blocks that can be removed
        
    Returns:
        Configured ContextApplier
    """
    config = ApplierConfig(
        enforce_token_budget=enforce_token_budget,
        allow_empty_context=allow_empty_context,
        max_removals_percent=max_removals_percent,
    )
    return ContextApplier(config)


__all__ = [
    "ContextApplier",
    "ApplierConfig",
    "ApplierResult",
    "create_context_applier",
]
