"""
Level-2 Semantic Action Intelligence Engine

Graph-driven semantic action engine that proposes semantic
completeness actions based on Level-2/3 diagnostics.

Answers: "Does the context contain the semantic information 
          required to be understood?"

This module exposes:
- SemanticActionEngine: Main orchestrator
- SemanticActionPlan: Output container
- SemanticAction, SemanticObligation, SemanticGap: Data types

Usage:
    from homllm.intelligence.actions.level2 import (
        SemanticActionEngine,
        SemanticActionPlan,
    )
    
    engine = SemanticActionEngine(enabled=True)
    plan = engine.propose(diagnostics, context)
"""

from homllm.intelligence.actions.level2.plan import (
    SemanticActionType,
    SemanticAction,
    SemanticObligation,
    SemanticGap,
    SemanticActionPlan,
    SEMANTIC_ACTION_NAMES,
    SEMANTIC_ACTION_ORDER,
)
from homllm.intelligence.actions.level2.graph import (
    NodeType,
    EdgeType,
    GraphNode,
    GraphEdge,
    SemanticGraph,
)
from homllm.intelligence.actions.level2.obligations import ObligationAnalyzer
from homllm.intelligence.actions.level2.gaps import GapDetector, RedundancyDetector
from homllm.intelligence.actions.level2.engine import (
    SemanticActionEngine,
    create_semantic_engine,
)


__all__ = [
    # Core engine
    "SemanticActionEngine",
    "create_semantic_engine",
    # Plan and actions
    "SemanticActionPlan",
    "SemanticAction",
    "SemanticActionType",
    "SemanticObligation",
    "SemanticGap",
    "SEMANTIC_ACTION_NAMES",
    "SEMANTIC_ACTION_ORDER",
    # Graph
    "SemanticGraph",
    "NodeType",
    "EdgeType",
    "GraphNode",
    "GraphEdge",
    # Analyzers
    "ObligationAnalyzer",
    "GapDetector",
    "RedundancyDetector",
]
