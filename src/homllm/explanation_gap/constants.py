"""
Structural Explanation Gap Detection — Versioned intent-to-depth table and rules (spec §6, §10).

Authoritative intent table; rule sets versioned. No learning; thresholds documented.
"""

from __future__ import annotations

import re

from homllm.explanation_gap.interfaces import DepthIntentType, DepthLabelType

# Version for audit
INTENT_TABLE_VERSION = "1.0"

# --- Intent-to-Depth Invariant Table (spec §6) ---
# (intent_class, default_label, mandatory_triggers_severity)
# Mandatory escalation triggers are implemented in rules.py; this table documents defaults.
INTENT_DEFAULT: dict[DepthIntentType, DepthLabelType] = {
    "FACTUAL": "SHALLOW_OK",
    "EXPLANATORY": "DETAILED_REQUIRED",
    "DEBUGGING": "DETAILED_REQUIRED",
    "ILLUSTRATIVE": "EXAMPLE_RECOMMENDED",
}

# --- Rule patterns (spec §4.1). Severity: EXAMPLE_RECOMMENDED > DETAILED_REQUIRED ---

# Illustrative: show / example / sample → EXAMPLE_RECOMMENDED
PATTERNS_EXAMPLE = re.compile(
    r"\b(show\s+me|example|sample\s+code|illustrate|demonstrate|"
    r"give\s+an?\s+example|code\s+sample|concrete\s+example)\b",
    re.IGNORECASE,
)

# Explanatory: why / how / explain / reason / step by / causal
PATTERNS_DETAILED = re.compile(
    r"\b(why\b|how\s+does|how\s+do\b|how\s+do\s+we|explain|reason\s+why|"
    r"step\s+by\s+step|step-by-step|causal|because\s+of|"
    r"what\s+causes|why\s+does|mechanism|underlying|"
    r"execution\s+flow|trace\s+.*\s+flow|through\s+all\s+layers?|lifecycle)\b",
    re.IGNORECASE,
)

# Debugging / behavioral: errors, execution paths, edge cases
PATTERNS_DEBUG = re.compile(
    r"\b(error|exception|fails?|happens\s+when|execution\s+path|"
    r"edge\s+case|failure\s+mode|debug|traceback|stack)\b",
    re.IGNORECASE,
)

# Factual: what-is style (no mandatory escalation; default SHALLOW_OK)
# No pattern that forces escalation; used only for default when no other intent matches.

# Order of application: check EXAMPLE first, then DETAILED, then DEBUG (so highest severity wins)
RULE_PATTERNS: list[tuple[DepthLabelType, re.Pattern[str]]] = [
    ("EXAMPLE_RECOMMENDED", PATTERNS_EXAMPLE),
    ("DETAILED_REQUIRED", PATTERNS_DETAILED),
    ("DETAILED_REQUIRED", PATTERNS_DEBUG),
]

# Cold-start: no history → medium confidence, low evidence
COLD_START_CONFIDENCE = 0.5
# Threshold above which history triggers escalation
HISTORY_ESCALATION_PCT = 0.3
# Embedding: min similarity to intent centroid to upgrade
EMBEDDING_UPGRADE_THRESHOLD = 0.6

# Seed phrases for intent centroids (Stage 2; spec §4.2)
SEED_ILLUSTRATIVE = "show me an example with code sample"
SEED_EXPLANATORY = "explain why and how it works step by step"
SEED_FACTUAL = "what is the definition"

__all__ = [
    "COLD_START_CONFIDENCE",
    "EMBEDDING_UPGRADE_THRESHOLD",
    "HISTORY_ESCALATION_PCT",
    "INTENT_DEFAULT",
    "INTENT_TABLE_VERSION",
    "PATTERNS_DEBUG",
    "PATTERNS_DETAILED",
    "PATTERNS_EXAMPLE",
    "RULE_PATTERNS",
    "SEED_EXPLANATORY",
    "SEED_FACTUAL",
    "SEED_ILLUSTRATIVE",
]
