"""
HOM-LLM Diagnostic Framework

A read-only observability system for understanding non-generation phases:
Embedding → Retrieval → Expansion → Re-ranking → Context Assembly

This system exists to EXPLAIN why the system behaves the way it does.

Core Constraints:
- No mutation of core HOM-LLM logic
- No imports that change runtime behavior  
- No feedback into retrieval, ranking, or context selection
- No dependency on LLM generation or prompts
- Strictly read-only
- Model-agnostic
- Deterministic and replayable
- Can be disabled or removed without affecting core system
"""

__version__ = "0.1.0"
