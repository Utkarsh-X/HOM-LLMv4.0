"""
Answer Structure Validator — Deterministic generation quality detection.

Checks answer structural completeness without LLM calls:
  A. Entity Coverage — does answer reference key components from context?
  B. Trace Completeness — flow questions must enumerate steps
  C. Comparative Structure — compare/tradeoff questions must have contrast markers
  D. Decorator/Wrapper Detection — context decorators must be mentioned

Output: structure scores (0-1 per dimension) stored as GENERATION_STRUCTURE_SCORE.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# ── Query classification patterns ──

TRACE_PATTERNS = re.compile(
    r'\b(trace|execution flow|lifecycle|step.by.step|flow|propagat|sequence)\b', re.I
)
COMPARE_PATTERNS = re.compile(
    r'\b(compare|tradeoff|trade.off|versus|vs\.?|difference|when to use|which|pros.and.cons)\b', re.I
)
BUG_PATTERNS = re.compile(
    r'\b(error|exception|fail|bug|handle|edge.case|what.happens.when|NaN|missing|invalid)\b', re.I
)


def classify_query_type(query_text: str) -> str:
    """Classify query into type for validation strategy selection."""
    if TRACE_PATTERNS.search(query_text):
        return "trace"
    if COMPARE_PATTERNS.search(query_text):
        return "comparison"
    if BUG_PATTERNS.search(query_text):
        return "error_handling"
    return "explanation"


# ── Entity extraction ──

def extract_entities_from_context(drop_trace: List[Dict]) -> List[str]:
    """Extract key entities (function names, class names) from context blocks."""
    entities = set()
    for block in drop_trace:
        if block.get("drop_reason") != "kept":
            continue
        # Extract symbol_id components
        symbol_id = block.get("symbol_id", "")
        if symbol_id:
            parts = symbol_id.replace("::", ".").split(".")
            for p in parts:
                clean = re.sub(r'[^a-zA-Z0-9_]', '', p)
                if clean and len(clean) >= 3 and not clean.startswith("__"):
                    entities.add(clean.lower())

        # Extract from content
        content = block.get("block_content", "") or ""
        # Function/class/method names
        for m in re.finditer(r'(?:def|class|function)\s+(\w+)', content):
            name = m.group(1).lower()
            if len(name) >= 3:
                entities.add(name)
        # Decorator names
        for m in re.finditer(r'@(\w+)', content):
            entities.add(m.group(1).lower())

    return list(entities)


def extract_entities_from_answer(answer_text: str) -> List[str]:
    """Extract referenced entities from answer text."""
    entities = set()
    # Code references (backtick-wrapped or camelCase/snake_case)
    for m in re.finditer(r'`(\w+)`', answer_text):
        entities.add(m.group(1).lower())
    for m in re.finditer(r'\b([a-z_][a-z0-9_]*(?:_[a-z0-9]+)+)\b', answer_text):
        if len(m.group(1)) >= 3:
            entities.add(m.group(1).lower())
    # CamelCase
    for m in re.finditer(r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b', answer_text):
        entities.add(m.group(1).lower())
    return list(entities)


# ── Dimension validators ──

def score_entity_coverage(context_entities: List[str], answer_entities: List[str]) -> float:
    """What fraction of context entities are mentioned in the answer?"""
    if not context_entities:
        return 1.0
    ctx_set = set(context_entities)
    ans_set = set(answer_entities)
    covered = len(ctx_set & ans_set)
    return min(1.0, covered / max(len(ctx_set), 1))


def score_trace_completeness(answer_text: str, query_type: str) -> float:
    """Does the answer enumerate steps for trace-type queries?"""
    if query_type != "trace":
        return 1.0  # N/A for non-trace queries

    # Look for step enumeration patterns
    step_markers = re.findall(
        r'(?:step\s*\d|^\s*\d+[\.\):]|\bfirst\b|\bthen\b|\bnext\b|\bfinally\b|→|->|==>)',
        answer_text, re.I | re.M
    )
    # A good trace should have 3+ steps
    step_count = len(step_markers)
    if step_count >= 5:
        return 1.0
    elif step_count >= 3:
        return 0.7
    elif step_count >= 1:
        return 0.4
    return 0.1


def score_comparative_structure(answer_text: str, query_type: str) -> float:
    """Does the answer contain contrast markers for comparison queries?"""
    if query_type != "comparison":
        return 1.0

    contrast_markers = re.findall(
        r'\b(however|whereas|in contrast|on the other hand|unlike|while|but|alternatively|'
        r'advantage|disadvantage|pro|con|tradeoff|trade.off|better|worse|faster|slower|'
        r'compared to|difference|similar|distinct)\b',
        answer_text, re.I
    )
    # Also check for tabular/list comparisons
    table_markers = len(re.findall(r'^\s*[-*]\s+\w+.*:', answer_text, re.M))

    markers = len(contrast_markers) + table_markers
    if markers >= 6:
        return 1.0
    elif markers >= 3:
        return 0.7
    elif markers >= 1:
        return 0.4
    return 0.1


def score_decorator_mention(drop_trace: List[Dict], answer_text: str) -> float:
    """If context has decorators/middleware, does answer mention them?"""
    context_decorators = set()
    for block in drop_trace:
        if block.get("drop_reason") != "kept":
            continue
        content = block.get("block_content", "") or ""
        for m in re.finditer(r'@(\w+)', content):
            context_decorators.add(m.group(1).lower())

    if not context_decorators:
        return 1.0  # N/A

    answer_lower = answer_text.lower()
    mentioned = sum(1 for d in context_decorators if d in answer_lower)
    return min(1.0, mentioned / max(len(context_decorators), 1))


# ── Evidence density ──

def score_evidence_density(answer_text: str) -> float:
    """Measures presence of concrete evidence references."""
    line_refs = len(re.findall(r'\bline\s*\d+', answer_text, re.I))
    func_refs = len(re.findall(r'`\w+`', answer_text))
    file_refs = len(re.findall(r'\b\w+\.\w{1,4}\b', answer_text))  # file.py patterns
    code_blocks = len(re.findall(r'```', answer_text))

    total = line_refs + func_refs + file_refs + code_blocks
    # Normalize: 20+ evidence refs = perfect
    return min(1.0, total / 20.0)


# ── Self-contradiction detection ──

def score_contradiction(answer_text: str) -> float:
    """Detect basic self-contradictions (higher = more contradictions = bad)."""
    # Contradiction patterns
    contras = re.findall(
        r'\b(however|but)\s+(?:.*?)\b(actually|in fact|contrary|wrong|incorrect|not true)\b',
        answer_text, re.I | re.S
    )
    negation_reversals = re.findall(
        r'\b(does not|doesn\'t|cannot|can\'t)\b.*?\b(does|can|will)\b',
        answer_text, re.I
    )
    hedging = re.findall(
        r'\b(might|perhaps|possibly|arguably|unclear|uncertain|not sure|speculation)\b',
        answer_text, re.I
    )

    total = len(contras) + len(negation_reversals) + len(hedging) * 0.5
    # Normalize: 5+ contradictions = very bad
    return min(1.0, total / 5.0)


# ── Answer depth ──

def score_answer_depth(answer_text: str, context_tokens: int) -> float:
    """Answer depth relative to context size."""
    answer_words = len(answer_text.split())
    # Good answers should be 30-70% context word count
    if context_tokens <= 0:
        context_tokens = 500
    ratio = answer_words / context_tokens
    if 0.3 <= ratio <= 1.5:
        return 1.0
    elif 0.15 <= ratio or ratio <= 2.0:
        return 0.6
    else:
        return 0.3


# ── Main validation function ──

def validate_answer(
    query_text: str,
    answer_text: str,
    drop_trace: List[Dict],
    context_tokens: int = 0,
) -> Dict[str, Any]:
    """Run all validators and return structured scores.

    Returns dict with scores (0-1) per dimension and overall structure_score.
    """
    query_type = classify_query_type(query_text)

    ctx_entities = extract_entities_from_context(drop_trace)
    ans_entities = extract_entities_from_answer(answer_text)

    scores = {
        "entity_coverage": score_entity_coverage(ctx_entities, ans_entities),
        "trace_completeness": score_trace_completeness(answer_text, query_type),
        "comparative_structure": score_comparative_structure(answer_text, query_type),
        "decorator_mention": score_decorator_mention(drop_trace, answer_text),
        "evidence_density": score_evidence_density(answer_text),
        "contradiction_score": score_contradiction(answer_text),
        "answer_depth": score_answer_depth(answer_text, context_tokens),
    }

    # Overall structure score (average of positive dimensions, minus contradiction)
    positive = [
        scores["entity_coverage"],
        scores["trace_completeness"],
        scores["comparative_structure"],
        scores["decorator_mention"],
        scores["evidence_density"],
        scores["answer_depth"],
    ]
    structure_score = sum(positive) / len(positive) - 0.3 * scores["contradiction_score"]
    structure_score = max(0.0, min(1.0, structure_score))

    return {
        "query_type": query_type,
        "structure_score": round(structure_score, 4),
        "dimensions": {k: round(v, 4) for k, v in scores.items()},
        "entity_stats": {
            "context_entities": len(ctx_entities),
            "answer_entities": len(ans_entities),
            "covered": len(set(ctx_entities) & set(ans_entities)),
        },
    }
