"""
Level-1 Alignment Observability Layer
Level-2 Failure Classification Layer
Level-3 Policy Decision Layer

Read-only, deterministic telemetry layer that exposes measurable
alignment signals between user query, assembled context, and
expected answer structure.

CONSTRAINTS (ABSOLUTE):
- Read-only (never modifies retrieval, ranking, or generation)
- Deterministic (same input → same output)
- Provider-agnostic (uses existing embedder)
- Disabled by default (zero runtime cost when off)
- Telemetry-only (no behavior changes)

USAGE:
    from homllm.alignment import create_alignment_analyzer
    
    analyzer = create_alignment_analyzer(embedder, enabled=True)
    report = analyzer.analyze(query, context, contract, readability)
    if report:
        telemetry = report.to_dict()
        
        # Level-2: Classify failures
        from homllm.alignment import create_alignment_classifier
        classifier = create_alignment_classifier()
        failure_report = classifier.classify(report)
        
        # Level-3: Policy decision
        from homllm.alignment.policy import create_policy_engine
        engine = create_policy_engine()
        decision = engine.decide(failure_report)
"""

from .interfaces import (
    AlignmentReport,
    SemanticAlignment,
    StructuralAlignment,
    GroundingAlignment,
    RiskIndicators,
)
from .analyzer import AlignmentAnalyzer
from .classifier import (
    FailureType,
    AlignmentFailureReport,
    AlignmentClassifier,
    create_alignment_classifier,
)
from .policy import (
    ResponsePolicy,
    PolicyDecision,
    AlignmentPolicyEngine,
    create_policy_engine,
)


def create_alignment_analyzer(
    embedder,
    enabled: bool = False,
) -> AlignmentAnalyzer:
    """
    Factory function to create AlignmentAnalyzer.
    
    Args:
        embedder: QwenEmbedder for semantic similarity computation
        enabled: Whether alignment analysis is active (default: False)
        
    Returns:
        Configured AlignmentAnalyzer instance
    """
    return AlignmentAnalyzer(embedder=embedder, enabled=enabled)


__all__ = [
    # Level-1 Data structures
    "AlignmentReport",
    "SemanticAlignment",
    "StructuralAlignment",
    "GroundingAlignment",
    "RiskIndicators",
    # Level-1 Analyzer
    "AlignmentAnalyzer",
    # Level-1 Factory
    "create_alignment_analyzer",
    # Level-2 Data structures
    "FailureType",
    "AlignmentFailureReport",
    # Level-2 Classifier
    "AlignmentClassifier",
    # Level-2 Factory
    "create_alignment_classifier",
    # Level-3 Data structures
    "ResponsePolicy",
    "PolicyDecision",
    # Level-3 Engine
    "AlignmentPolicyEngine",
    # Level-3 Factory
    "create_policy_engine",
]


