"""
Level-3 Cognitive Action Planner

Converts observations into ordered cognitive shaping actions.
Final stage before output.

CONSTRAINTS (ABSOLUTE):
- Deterministic ordering
- No LLM or ML
- Every action is auditable
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homllm.intelligence.actions.level3.plan import (
    CognitiveAction,
    CognitiveActionType,
    CognitiveActionPlan,
    ReasoningPath,
    InvariantProtection,
    AmbiguityIsolation,
    COGNITIVE_ACTION_ORDER,
)

if TYPE_CHECKING:
    from homllm.intelligence.interfaces import DiagnosticSnapshot


class CognitiveActionPlanner:
    """
    Converts observations into ordered cognitive shaping actions.
    
    Merges actions from:
    - Load regulator
    - Invariant controller
    
    Produces final ordered CognitiveActionPlan.
    """
    
    def __init__(self):
        pass
    
    def plan(
        self,
        load_actions: list[CognitiveAction],
        invariant_actions: list[CognitiveAction],
        paths: tuple[ReasoningPath, ...],
        invariants: tuple[InvariantProtection, ...],
        ambiguities: tuple[AmbiguityIsolation, ...],
        diagnostics,
    ) -> CognitiveActionPlan:
        """
        Create final cognitive action plan.
        
        Args:
            load_actions: Actions from load regulator
            invariant_actions: Actions from invariant controller
            paths: Extracted reasoning paths
            invariants: Protected invariants
            ambiguities: Isolated ambiguities
            diagnostics: For additional context
            
        Returns:
            Complete CognitiveActionPlan
        """
        # 1. Merge all actions
        all_actions = load_actions + invariant_actions
        
        # 2. Deduplicate by target (keep highest priority)
        deduped_actions = self._deduplicate_actions(all_actions)
        
        # 3. Order actions by type priority
        ordered_actions = self._order_actions(deduped_actions)
        
        # 4. Build explanations
        explanations = self._build_explanations(
            ordered_actions,
            paths,
            invariants,
            ambiguities,
        )
        
        # 5. Compute statistics
        max_complexity = max(
            (p.complexity for p in paths),
            default=0
        )
        
        return CognitiveActionPlan(
            actions=ordered_actions,
            reasoning_paths=paths,
            invariants=invariants,
            ambiguities=ambiguities,
            explanations=tuple(explanations),
            total_paths=len(paths),
            max_path_complexity=max_complexity,
            invariant_count=len(invariants),
            ambiguity_count=len(ambiguities),
        )
    
    def _deduplicate_actions(
        self,
        actions: list[CognitiveAction],
    ) -> list[CognitiveAction]:
        """Deduplicate actions by target, keeping highest priority."""
        seen: dict[str, CognitiveAction] = {}
        
        for action in actions:
            key = f"{action.action_type.name}:{action.target}"
            
            if key not in seen:
                seen[key] = action
            elif action.priority < seen[key].priority:
                # Higher priority (lower number) wins
                seen[key] = action
        
        return list(seen.values())
    
    def _order_actions(
        self,
        actions: list[CognitiveAction],
    ) -> tuple[CognitiveAction, ...]:
        """Order actions by type priority."""
        type_priority = {t: i for i, t in enumerate(COGNITIVE_ACTION_ORDER)}
        
        sorted_actions = sorted(
            actions,
            key=lambda a: (
                type_priority.get(a.action_type, 99),
                a.target,  # Stable secondary sort
            )
        )
        
        return tuple(sorted_actions)
    
    def _build_explanations(
        self,
        actions: tuple[CognitiveAction, ...],
        paths: tuple[ReasoningPath, ...],
        invariants: tuple[InvariantProtection, ...],
        ambiguities: tuple[AmbiguityIsolation, ...],
    ) -> list[str]:
        """Build human-readable explanations."""
        explanations = []
        
        # Path summary
        if paths:
            max_complexity = max(p.complexity for p in paths)
            explanations.append(
                f"Extracted {len(paths)} reasoning paths (max complexity: {max_complexity})"
            )
        
        # Invariant summary
        if invariants:
            explanations.append(f"Protecting {len(invariants)} invariants")
        
        # Ambiguity summary
        if ambiguities:
            explanations.append(f"Isolating {len(ambiguities)} ambiguous regions")
        
        # Action summary by type
        action_counts: dict[str, int] = {}
        for action in actions:
            name = action.type_name
            action_counts[name] = action_counts.get(name, 0) + 1
        
        for name, count in action_counts.items():
            explanations.append(f"{name}: {count} action(s)")
        
        return explanations


__all__ = [
    "CognitiveActionPlanner",
]
