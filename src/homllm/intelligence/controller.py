"""
Intelligence Controller

The SINGLE orchestration component that coordinates:
1. Diagnostic Engine (L1-L3)
2. Action Engines (L1-L3)

This controller is a CONDUCTOR, not a THINKER.
It calls subsystems in order, collects outputs, and returns a merged plan.

DESIGN CONSTRAINTS (ABSOLUTE):
- No action logic (all intelligence lives in engines)
- No interpretation of diagnostic results
- No context mutation
- No retries or loops
- No state across calls
- No learning, caching, or history
- No LLM calls
- No heuristics or rules
- Deterministic: same input → same output
- Query-scoped: operates on one ContextArtifact at a time
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Any

if TYPE_CHECKING:
    from homllm.context.interfaces import ContextArtifact

# Import diagnostic controller
from homllm.intelligence.diagnostics.controller import (
    DiagnosticController,
    create_diagnostic_provider,
)
from homllm.intelligence.interfaces import DiagnosticSnapshot

# Import action engines
from homllm.intelligence.actions.level1.engine import Level1ActionEngine
from homllm.intelligence.actions.level2.engine import SemanticActionEngine
from homllm.intelligence.actions.level3.engine import Level3ActionEngine

# Import plan types for wrapping
from homllm.intelligence.actions.level1.plan import (
    ContextModificationPlan as L1Plan,
    Action as L1Action,
)
from homllm.intelligence.actions.level2.plan import (
    SemanticActionPlan,
    SemanticAction,
)
from homllm.intelligence.actions.level3.plan import (
    CognitiveActionPlan,
    CognitiveAction,
)


# =============================================================================
# UNIFIED OUTPUT TYPES
# =============================================================================

@dataclass(frozen=True)
class UnifiedAction:
    """
    A unified action representation from any engine level.
    
    Preserves the original action while adding level attribution.
    Does NOT interpret or transform actions.
    """
    
    level: int  # 1, 2, or 3
    action_type: str  # Human-readable type name
    target: str  # block_id, concept, or reasoning path
    priority: int  # Original priority value
    justification: str  # Why this action is proposed
    source_engine: str  # "level1", "level2", "level3"
    original_action: Any  # Reference to original action object


@dataclass
class ContextModificationPlan:
    """
    The UNIFIED output of the IntelligenceController.
    
    Aggregates outputs from all action levels into a single,
    deterministic, auditable, serializable, and reversible plan.
    
    Structure:
        ContextModificationPlan
        ├── level1_plan: L1Plan (structural actions)
        ├── level2_plan: SemanticActionPlan (semantic actions)
        ├── level3_plan: CognitiveActionPlan (cognitive shaping)
        ├── unified_actions: Merged and ordered actions
        └── metadata: Execution statistics
    
    Guarantees:
    - Deterministic: same input → same output
    - Auditable: full provenance trail
    - Serializable: can be JSON-encoded
    - Reversible: actions can be undone
    - No side effects: context is not modified
    """
    
    # Individual level plans (unmodified)
    level1_plan: L1Plan
    level2_plan: SemanticActionPlan
    level3_plan: CognitiveActionPlan
    
    # Unified ordered actions
    unified_actions: tuple[UnifiedAction, ...]
    
    # Metadata
    diagnostics_available: bool = True
    levels_executed: tuple[int, ...] = ()
    total_actions: int = 0
    
    @classmethod
    def empty(cls) -> "ContextModificationPlan":
        """Create an empty plan (for no diagnostics or all engines disabled)."""
        return cls(
            level1_plan=L1Plan.empty(),
            level2_plan=SemanticActionPlan.empty(),
            level3_plan=CognitiveActionPlan.empty(),
            unified_actions=(),
            diagnostics_available=False,
            levels_executed=(),
            total_actions=0,
        )
    
    @property
    def is_empty(self) -> bool:
        """Check if plan contains no actions."""
        return self.total_actions == 0
    
    def to_dict(self) -> dict:
        """
        Serialize plan to dictionary for auditing.
        
        Returns JSON-serializable representation.
        """
        return {
            "diagnostics_available": self.diagnostics_available,
            "levels_executed": list(self.levels_executed),
            "total_actions": self.total_actions,
            "level1": {
                "action_count": len(self.level1_plan.actions),
                "summary": self.level1_plan.summary,
                "conflicts_resolved": self.level1_plan.conflicts_resolved,
            },
            "level2": {
                "action_count": len(self.level2_plan.actions),
                "total_obligations": self.level2_plan.total_obligations,
                "satisfied_obligations": self.level2_plan.satisfied_obligations,
                "gap_count": self.level2_plan.total_gaps,
            },
            "level3": {
                "action_count": len(self.level3_plan.actions),
                "path_count": self.level3_plan.total_paths,
                "invariant_count": self.level3_plan.invariant_count,
                "ambiguity_count": self.level3_plan.ambiguity_count,
            },
            "unified_actions": [
                {
                    "level": a.level,
                    "type": a.action_type,
                    "target": a.target,
                    "priority": a.priority,
                    "justification": a.justification,
                }
                for a in self.unified_actions
            ],
        }


# =============================================================================
# INTELLIGENCE CONTROLLER
# =============================================================================

class IntelligenceController:
    """
    The SINGLE runtime integration point for the Intelligence system.
    
    Orchestrates:
    1. Diagnostic Engine → produces DiagnosticSnapshot
    2. Level-1 Action Engine → structural actions
    3. Level-2 Action Engine → semantic actions
    4. Level-3 Action Engine → cognitive shaping
    
    This controller is:
    - NOT an agent
    - NOT a planner
    - NOT intelligent
    - NOT adaptive
    
    It is a CONDUCTOR, not a THINKER.
    
    Usage:
        controller = IntelligenceController(
            level1_enabled=True,
            level2_enabled=True,
            level3_enabled=True,
        )
        plan = controller.run(context_artifact)
        
        # Plan is deterministic and auditable
        print(plan.to_dict())
    
    Attributes:
        level1_enabled: Whether Level-1 structural engine runs
        level2_enabled: Whether Level-2 semantic engine runs
        level3_enabled: Whether Level-3 cognitive engine runs
    """
    
    def __init__(
        self,
        diagnostic_controller: Optional[DiagnosticController] = None,
        level1_engine: Optional[Level1ActionEngine] = None,
        level2_engine: Optional[SemanticActionEngine] = None,
        level3_engine: Optional[Level3ActionEngine] = None,
        *,
        level1_enabled: bool = True,
        level2_enabled: bool = True,
        level3_enabled: bool = True,
    ):
        """
        Initialize the controller.
        
        Args:
            diagnostic_controller: Optional DiagnosticController instance.
                                   If None, creates a default one.
            level1_engine: Optional Level1ActionEngine instance.
                           If None, creates a default one.
            level2_engine: Optional SemanticActionEngine instance.
                           If None, creates a default one.
            level3_engine: Optional Level3ActionEngine instance.
                           If None, creates a default one.
            level1_enabled: Whether to run Level-1 engine. Default True.
            level2_enabled: Whether to run Level-2 engine. Default True.
            level3_enabled: Whether to run Level-3 engine. Default True.
        """
        # Instantiate defaults if not provided
        self._diagnostic_controller = (
            diagnostic_controller 
            if diagnostic_controller is not None 
            else create_diagnostic_provider()
        )
        
        self._level1_engine = (
            level1_engine 
            if level1_engine is not None 
            else Level1ActionEngine(enabled=level1_enabled)
        )
        
        self._level2_engine = (
            level2_engine 
            if level2_engine is not None 
            else SemanticActionEngine(enabled=level2_enabled)
        )
        
        self._level3_engine = (
            level3_engine 
            if level3_engine is not None 
            else Level3ActionEngine(enabled=level3_enabled)
        )
        
        # Store enabled flags (used for metadata)
        self._level1_enabled = level1_enabled
        self._level2_enabled = level2_enabled
        self._level3_enabled = level3_enabled
    
    def run(self, context: "ContextArtifact") -> ContextModificationPlan:
        """
        Execute the intelligence pipeline on a context artifact.
        
        Flow:
        1. Run diagnostics once → DiagnosticSnapshot
        2. If diagnostics unavailable → return empty plan
        3. Invoke enabled action engines in strict order (L1 → L2 → L3)
        4. Pass SAME diagnostic snapshot to all engines
        5. Merge plans deterministically
        6. Return unified plan
        
        Args:
            context: ContextArtifact to analyze
            
        Returns:
            ContextModificationPlan with all proposed actions.
            Empty plan if diagnostics unavailable.
            
        Note:
            - Context is NEVER mutated
            - Same input always produces same output
            - No side effects
        """
        # Step 1: Run diagnostics ONCE
        try:
            snapshot = self._diagnostic_controller.analyze(context)
        except Exception:
            # Diagnostics failed - return empty plan, do NOT raise
            return ContextModificationPlan.empty()
        
        # Step 2: Check if diagnostics are available
        # If ALL levels are unavailable, return empty plan
        if (
            snapshot.level1.status != "available" and
            snapshot.level2.status != "available" and
            snapshot.level3.status != "available"
        ):
            return ContextModificationPlan.empty()
        
        # Step 3: Invoke action engines in STRICT order
        # Each engine receives the SAME snapshot
        
        level1_plan: L1Plan = L1Plan.empty()
        level2_plan: SemanticActionPlan = SemanticActionPlan.empty()
        level3_plan: CognitiveActionPlan = CognitiveActionPlan.empty()
        levels_executed: list[int] = []
        
        # Level-1: Structural Actions
        if self._level1_enabled:
            level1_plan = self._level1_engine.propose(snapshot, context)
            levels_executed.append(1)
        
        # Level-2: Semantic Actions
        if self._level2_enabled:
            level2_plan = self._level2_engine.propose(snapshot, context)
            levels_executed.append(2)
        
        # Level-3: Cognitive Actions
        if self._level3_enabled:
            level3_plan = self._level3_engine.propose(snapshot, context)
            levels_executed.append(3)
        
        # Step 4: Merge plans deterministically
        unified_actions = self._merge_plans(level1_plan, level2_plan, level3_plan)
        
        # Step 5: Return unified plan
        return ContextModificationPlan(
            level1_plan=level1_plan,
            level2_plan=level2_plan,
            level3_plan=level3_plan,
            unified_actions=unified_actions,
            diagnostics_available=True,
            levels_executed=tuple(levels_executed),
            total_actions=len(unified_actions),
        )
    
    def _merge_plans(
        self,
        level1_plan: L1Plan,
        level2_plan: SemanticActionPlan,
        level3_plan: CognitiveActionPlan,
    ) -> tuple[UnifiedAction, ...]:
        """
        Merge action plans from all levels into a unified action list.
        
        Ordering:
        1. Level-1 actions first (structural foundation)
        2. Level-2 actions second (semantic completeness)
        3. Level-3 actions third (cognitive shaping)
        
        Within each level, actions are ordered by their original priority.
        
        Conflict Resolution:
        - No conflict resolution at merge time
        - Each level operates on different dimensions
        - Level-1: blocks (structural)
        - Level-2: concepts (semantic)
        - Level-3: reasoning paths (cognitive)
        
        Returns:
            Tuple of UnifiedAction in deterministic order.
        """
        unified: list[UnifiedAction] = []
        
        # Level-1 actions (structural)
        for action in level1_plan.actions:
            unified.append(UnifiedAction(
                level=1,
                action_type=action.type_name,
                target=action.block_id,
                priority=action.priority,
                justification=action.reason,
                source_engine="level1",
                original_action=action,
            ))
        
        # Level-2 actions (semantic)
        for action in level2_plan.actions:
            unified.append(UnifiedAction(
                level=2,
                action_type=action.type_name,
                target=action.target,
                priority=action.priority,
                justification=action.justification,
                source_engine="level2",
                original_action=action,
            ))
        
        # Level-3 actions (cognitive)
        for action in level3_plan.actions:
            unified.append(UnifiedAction(
                level=3,
                action_type=action.type_name,
                target=action.target,
                priority=action.priority,
                justification=action.justification,
                source_engine="level3",
                original_action=action,
            ))
        
        # Sort deterministically:
        # Primary: level (1 before 2 before 3)
        # Secondary: priority within level (lower = higher priority)
        # Tertiary: action_type for stability
        # Quaternary: target for final stability
        unified.sort(key=lambda a: (a.level, a.priority, a.action_type, a.target))
        
        return tuple(unified)


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_intelligence_controller(
    diagnostic_controller: Optional[DiagnosticController] = None,
    level1_engine: Optional[Level1ActionEngine] = None,
    level2_engine: Optional[SemanticActionEngine] = None,
    level3_engine: Optional[Level3ActionEngine] = None,
    *,
    level1_enabled: bool = True,
    level2_enabled: bool = True,
    level3_enabled: bool = True,
) -> IntelligenceController:
    """
    Factory function to create an IntelligenceController.
    
    Args:
        diagnostic_controller: Optional diagnostic controller
        level1_engine: Optional Level-1 engine
        level2_engine: Optional Level-2 engine
        level3_engine: Optional Level-3 engine
        level1_enabled: Enable Level-1 engine
        level2_enabled: Enable Level-2 engine
        level3_enabled: Enable Level-3 engine
        
    Returns:
        Configured IntelligenceController
    """
    return IntelligenceController(
        diagnostic_controller=diagnostic_controller,
        level1_engine=level1_engine,
        level2_engine=level2_engine,
        level3_engine=level3_engine,
        level1_enabled=level1_enabled,
        level2_enabled=level2_enabled,
        level3_enabled=level3_enabled,
    )


__all__ = [
    "IntelligenceController",
    "ContextModificationPlan",
    "UnifiedAction",
    "create_intelligence_controller",
]
