"""
Level-1 Action Intelligence Engine

Structural optimization engine that proposes context modifications
based on Level-1 diagnostics. Pure, deterministic, auditable.

This module exposes:
- Level1ActionEngine: Main orchestrator
- ContextModificationPlan: Output container
- Action, ActionType: Action primitives

Usage:
    from homllm.intelligence.actions.level1 import (
        Level1ActionEngine,
        ContextModificationPlan,
    )
    
    engine = Level1ActionEngine(enabled=True)
    plan = engine.propose(diagnostics, context)
"""

from homllm.intelligence.actions.level1.plan import (
    Action,
    ActionType,
    ProposedAction,
    ContextModificationPlan,
    ACTION_TYPE_NAMES,
    ACTION_GLOBAL_ORDER,
)
from homllm.intelligence.actions.level1.engine import (
    Level1ActionEngine,
    create_level1_engine,
)
from homllm.intelligence.actions.level1.resolver import (
    ConflictResolver,
    order_actions,
)
from homllm.intelligence.actions.level1.rules import get_all_rules


__all__ = [
    # Core engine
    "Level1ActionEngine",
    "create_level1_engine",
    # Plan and actions
    "ContextModificationPlan",
    "Action",
    "ActionType",
    "ProposedAction",
    "ACTION_TYPE_NAMES",
    "ACTION_GLOBAL_ORDER",
    # Internals (for testing)
    "ConflictResolver",
    "order_actions",
    "get_all_rules",
]
