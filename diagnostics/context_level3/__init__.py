"""
Level-3 Context Cognitive Diagnostics

Explains why context succeeds or fails for a specific query,
focusing on semantic alignment, explanatory completeness, and cognitive load.

CONSTRAINTS:
- No mutation of core HOM-LLM logic
- No feedback into retrieval, ranking, or context selection
- No ML models or LLM calls
- Deterministic heuristics only
- Read-only analysis

Modules:
1. Query Intent Decomposition
2. Explanatory Role Classification
3. Concept Coverage & Gap Detection
4. Cognitive Load Estimation
5. Alignment Summary
"""

from diagnostics.context_level3.inspect_query_intent import (
    QueryIntentAnalyzer,
    QueryIntent,
)
from diagnostics.context_level3.inspect_explanatory_roles import (
    ExplanatoryRoleAnalyzer,
    BlockRole,
    ExplanatoryRole,
)
from diagnostics.context_level3.inspect_concept_gaps import (
    ConceptGapAnalyzer,
    ConceptGapResult,
)
from diagnostics.context_level3.inspect_cognitive_load import (
    CognitiveLoadAnalyzer,
    CognitiveLoadResult,
)
from diagnostics.context_level3.inspect_alignment_summary import (
    AlignmentSummaryAnalyzer,
    Level3DiagnosticResult,
    format_level3_diagnostic,
)

__all__ = [
    "QueryIntentAnalyzer",
    "QueryIntent",
    "ExplanatoryRoleAnalyzer",
    "BlockRole",
    "ExplanatoryRole",
    "ConceptGapAnalyzer",
    "ConceptGapResult",
    "CognitiveLoadAnalyzer",
    "CognitiveLoadResult",
    "AlignmentSummaryAnalyzer",
    "Level3DiagnosticResult",
    "format_level3_diagnostic",
]
