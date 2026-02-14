"""
Module 1: Query Intent Decomposition

Converts a query into semantic obligations that the context must satisfy.

Outputs:
- Required concepts
- Required actions
- Required explanation types
- Intent classification (WHAT/HOW/WHY/COMPARE)

CONSTRAINTS:
- Deterministic heuristics only
- No ML/LLM
- Read-only
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import re


class IntentType(Enum):
    """Classification of query intent."""
    WHAT = "what"           # Request for definition/description
    HOW = "how"             # Request for mechanism/process
    WHY = "why"             # Request for reasoning/purpose
    COMPARE = "compare"     # Request for comparison
    TRACE = "trace"         # Request to follow flow/execution
    RESOLVE = "resolve"     # Request to fix/debug
    UNKNOWN = "unknown"


class ActionVerb(Enum):
    """Classified action verbs from query."""
    EXPLAIN = "explain"
    RESOLVE = "resolve"
    COMPARE = "compare"
    TRACE = "trace"
    DESCRIBE = "describe"
    IMPLEMENT = "implement"
    DEBUG = "debug"
    FIND = "find"
    LIST = "list"
    SHOW = "show"


@dataclass
class QueryIntent:
    """Decomposed query intent."""
    
    # Primary intent type
    intent_type: IntentType = IntentType.UNKNOWN
    
    # Secondary intent (may be composite)
    secondary_type: Optional[IntentType] = None
    
    # Required concepts (nouns, identifiers)
    concepts: list[str] = field(default_factory=list)
    
    # Required actions (verbs)
    actions: list[ActionVerb] = field(default_factory=list)
    
    # Explanation mode
    is_explanatory: bool = False
    is_comparative: bool = False
    is_procedural: bool = False
    
    # Original query
    query_text: str = ""


class QueryIntentAnalyzer:
    """
    Analyzes query text to extract semantic obligations.
    
    Uses deterministic heuristics:
    - Verb classification
    - Noun phrase extraction
    - Identifier detection
    - Intent pattern matching
    """
    
    # Verb to action mapping
    VERB_ACTIONS = {
        # Explanatory
        "explain": ActionVerb.EXPLAIN,
        "describe": ActionVerb.DESCRIBE,
        "what": ActionVerb.DESCRIBE,
        "show": ActionVerb.SHOW,
        "tell": ActionVerb.EXPLAIN,
        
        # Problem-solving
        "fix": ActionVerb.RESOLVE,
        "debug": ActionVerb.DEBUG,
        "resolve": ActionVerb.RESOLVE,
        "solve": ActionVerb.RESOLVE,
        "troubleshoot": ActionVerb.DEBUG,
        
        # Comparative
        "compare": ActionVerb.COMPARE,
        "differ": ActionVerb.COMPARE,
        "versus": ActionVerb.COMPARE,
        "vs": ActionVerb.COMPARE,
        
        # Tracing
        "trace": ActionVerb.TRACE,
        "follow": ActionVerb.TRACE,
        "track": ActionVerb.TRACE,
        "flow": ActionVerb.TRACE,
        
        # Implementation
        "implement": ActionVerb.IMPLEMENT,
        "create": ActionVerb.IMPLEMENT,
        "build": ActionVerb.IMPLEMENT,
        "add": ActionVerb.IMPLEMENT,
        
        # Discovery
        "find": ActionVerb.FIND,
        "locate": ActionVerb.FIND,
        "search": ActionVerb.FIND,
        "list": ActionVerb.LIST,
    }
    
    # Intent patterns
    WHAT_PATTERNS = [
        r"\bwhat\s+is\b",
        r"\bwhat\s+does\b",
        r"\bwhat\s+are\b",
        r"\bdefine\b",
        r"\bdescribe\b",
    ]
    
    HOW_PATTERNS = [
        r"\bhow\s+does\b",
        r"\bhow\s+do\b",
        r"\bhow\s+to\b",
        r"\bhow\s+can\b",
        r"\bprocess\b",
        r"\bmechanism\b",
    ]
    
    WHY_PATTERNS = [
        r"\bwhy\s+does\b",
        r"\bwhy\s+do\b",
        r"\bwhy\s+is\b",
        r"\breason\b",
        r"\bpurpose\b",
        r"\bcause\b",
    ]
    
    COMPARE_PATTERNS = [
        r"\bcompare\b",
        r"\bdifference\s+between\b",
        r"\bvs\.?\b",
        r"\bversus\b",
        r"\bor\b.*\bor\b",
    ]
    
    # Identifier patterns
    SNAKE_CASE = re.compile(r'\b[a-z][a-z0-9]*(_[a-z0-9]+)+\b')
    CAMEL_CASE = re.compile(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b')
    UPPER_SNAKE = re.compile(r'\b[A-Z][A-Z0-9]*(_[A-Z0-9]+)+\b')
    
    def analyze(self, query: str) -> QueryIntent:
        """
        Analyze query text to extract intent.
        
        Args:
            query: Raw query text
            
        Returns:
            QueryIntent with decomposed semantic obligations
        """
        query_lower = query.lower()
        
        result = QueryIntent(query_text=query)
        
        # 1. Classify intent type
        result.intent_type = self._classify_intent(query_lower)
        
        # 2. Extract actions from verbs
        result.actions = self._extract_actions(query_lower)
        
        # 3. Extract concepts (nouns and identifiers)
        result.concepts = self._extract_concepts(query)
        
        # 4. Set explanation modes
        result.is_explanatory = self._is_explanatory(query_lower, result.actions)
        result.is_comparative = self._is_comparative(query_lower)
        result.is_procedural = self._is_procedural(query_lower, result.actions)
        
        # 5. Detect secondary intent
        if result.is_explanatory and result.is_comparative:
            result.secondary_type = IntentType.COMPARE
        elif result.is_procedural:
            result.secondary_type = IntentType.HOW
        
        return result
    
    def _classify_intent(self, query: str) -> IntentType:
        """Classify primary intent type."""
        # Check patterns in order of specificity
        for pattern in self.COMPARE_PATTERNS:
            if re.search(pattern, query):
                return IntentType.COMPARE
        
        for pattern in self.WHY_PATTERNS:
            if re.search(pattern, query):
                return IntentType.WHY
        
        for pattern in self.HOW_PATTERNS:
            if re.search(pattern, query):
                return IntentType.HOW
        
        for pattern in self.WHAT_PATTERNS:
            if re.search(pattern, query):
                return IntentType.WHAT
        
        # Check for trace/resolve hints
        if any(word in query for word in ["trace", "flow", "follow", "call"]):
            return IntentType.TRACE
        
        if any(word in query for word in ["fix", "debug", "resolve", "error", "bug"]):
            return IntentType.RESOLVE
        
        return IntentType.UNKNOWN
    
    def _extract_actions(self, query: str) -> list[ActionVerb]:
        """Extract action verbs from query."""
        actions = []
        words = query.split()
        
        for word in words:
            # Clean punctuation
            clean_word = re.sub(r'[^\w]', '', word)
            if clean_word in self.VERB_ACTIONS:
                action = self.VERB_ACTIONS[clean_word]
                if action not in actions:
                    actions.append(action)
        
        return actions
    
    def _extract_concepts(self, query: str) -> list[str]:
        """Extract concepts from query."""
        concepts = []
        
        # Extract identifier-like patterns
        for pattern in [self.SNAKE_CASE, self.CAMEL_CASE, self.UPPER_SNAKE]:
            matches = pattern.findall(query)
            concepts.extend(matches)
        
        # Extract quoted strings
        quoted = re.findall(r'["\']([^"\']+)["\']', query)
        concepts.extend(quoted)
        
        # Extract backtick code references
        backtick = re.findall(r'`([^`]+)`', query)
        concepts.extend(backtick)

        # Fallback: extract meaningful tokens from natural language
        token_matches = re.findall(r"\b[A-Za-z0-9_]+\b", query)
        l_level_matches = re.findall(r"\bL\d+\b", query)
        token_matches.extend(l_level_matches)
        stopwords = {
            "what", "when", "where", "which", "who", "whom", "why", "how",
            "does", "do", "did", "is", "are", "was", "were", "be", "been",
            "the", "a", "an", "and", "or", "but", "if", "then", "than",
            "this", "that", "these", "those", "with", "without", "about",
            "into", "from", "to", "of", "for", "in", "on", "at", "by",
            "all", "any", "each", "every", "some", "most", "many", "few",
            "miss", "misses", "work", "working", "happens", "happen",
            "explain", "describe", "show", "tell", "trace", "resolve",
        }
        for token in token_matches:
            if len(token) < 2:
                continue
            token_lower = token.lower()
            if token_lower in stopwords:
                continue
            concepts.append(token)
        
        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for c in concepts:
            if c.lower() not in seen:
                seen.add(c.lower())
                unique.append(c)

        return unique
    
    def _is_explanatory(self, query: str, actions: list[ActionVerb]) -> bool:
        """Check if query requires explanation."""
        explanatory_actions = {ActionVerb.EXPLAIN, ActionVerb.DESCRIBE, ActionVerb.SHOW}
        if any(a in explanatory_actions for a in actions):
            return True
        
        explanatory_words = ["explain", "what", "describe", "tell", "understand"]
        return any(word in query for word in explanatory_words)
    
    def _is_comparative(self, query: str) -> bool:
        """Check if query requires comparison."""
        return any(re.search(p, query) for p in self.COMPARE_PATTERNS)
    
    def _is_procedural(self, query: str, actions: list[ActionVerb]) -> bool:
        """Check if query requires procedural explanation."""
        procedural_actions = {ActionVerb.IMPLEMENT, ActionVerb.TRACE}
        if any(a in procedural_actions for a in actions):
            return True
        
        return "how" in query


def format_query_intent(intent: QueryIntent) -> str:
    """Format query intent for display."""
    lines = []
    
    lines.append("Intent:")
    
    # Type
    type_str = intent.intent_type.value
    if intent.secondary_type:
        type_str += f" + {intent.secondary_type.value}"
    
    modes = []
    if intent.is_explanatory:
        modes.append("explanatory")
    if intent.is_comparative:
        modes.append("comparative")
    if intent.is_procedural:
        modes.append("procedural")
    
    if modes:
        type_str += f" ({', '.join(modes)})"
    
    lines.append(f"  type: {type_str}")
    
    # Concepts
    if intent.concepts:
        lines.append(f"  concepts: [{', '.join(intent.concepts)}]")
    
    # Actions
    if intent.actions:
        action_names = [a.value for a in intent.actions]
        lines.append(f"  actions: [{', '.join(action_names)}]")
    
    return "\n".join(lines)
