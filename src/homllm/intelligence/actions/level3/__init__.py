"""
Level-3 Cognitive Action Intelligence Engine

A reasoning compiler that shapes reasoning topology so the LLM
reasons correctly by default.

This is NOT an agent. It is a deterministic shaping system.

Exports:
- Level3ActionEngine: Main orchestrator
- CognitiveActionPlan: Output container
- CognitiveGraph: Reasoning topology graph
- Supporting types and utilities

Usage:
    from homllm.intelligence.actions.level3 import (
        Level3ActionEngine,
        CognitiveActionPlan,
    )
    
    engine = Level3ActionEngine(enabled=True)
    plan = engine.propose(diagnostics, context)
"""

from homllm.intelligence.actions.level3.plan import (
    CognitiveActionType,
    CognitiveAction,
    ReasoningStep,
    ReasoningPath,
    InvariantProtection,
    AmbiguityIsolation,
    CognitiveActionPlan,
    COGNITIVE_ACTION_NAMES,
    COGNITIVE_ACTION_ORDER,
)
from homllm.intelligence.actions.level3.graph import (
    CognitiveNodeType,
    CognitiveEdgeType,
    CognitiveNode,
    CognitiveEdge,
    CognitiveGraph,
)
from homllm.intelligence.actions.level3.paths import ReasoningPathExtractor
from homllm.intelligence.actions.level3.load import CognitiveLoadRegulator
from homllm.intelligence.actions.level3.invariants import InvariantController
from homllm.intelligence.actions.level3.planner import CognitiveActionPlanner
from homllm.intelligence.actions.level3.engine import (
    Level3ActionEngine,
    create_level3_engine,
)


__all__ = [
    # Core engine
    "Level3ActionEngine",
    "create_level3_engine",
    # Plan and actions
    "CognitiveActionPlan",
    "CognitiveAction",
    "CognitiveActionType",
    "ReasoningStep",
    "ReasoningPath",
    "InvariantProtection",
    "AmbiguityIsolation",
    "COGNITIVE_ACTION_NAMES",
    "COGNITIVE_ACTION_ORDER",
    # Graph
    "CognitiveGraph",
    "CognitiveNodeType",
    "CognitiveEdgeType",
    "CognitiveNode",
    "CognitiveEdge",
    # Components
    "ReasoningPathExtractor",
    "CognitiveLoadRegulator",
    "InvariantController",
    "CognitiveActionPlanner",
]
