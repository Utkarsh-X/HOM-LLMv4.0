"""
Token Attribution Telemetry Module.

Provides opt-in token attribution metrics to understand where input tokens come from.
This is diagnostic instrumentation only - no behavior changes.

Metrics:
- visible_prompt_tokens: Token count of final rendered prompt
- context_tokens_after_intelligence: From ContextArtifact.used_tokens
- template_tokens: Tokenized template without query/context  
- query_tokens: Tokenized raw query
- estimated_hidden_provider_tokens: tokens_in - visible_prompt_tokens (if available)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import re


@dataclass(frozen=True)
class TokenAttribution:
    """Token attribution metrics for a single query run.
    
    All values are token counts (integers) except estimated_hidden_provider_tokens
    which may be None if the provider doesn't report tokens_in.
    """
    visible_prompt_tokens: int
    context_tokens_after_intelligence: int
    template_tokens: int
    query_tokens: int
    estimated_hidden_provider_tokens: Optional[int]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for telemetry output."""
        return {
            "visible_prompt_tokens": self.visible_prompt_tokens,
            "context_tokens_after_intelligence": self.context_tokens_after_intelligence,
            "template_tokens": self.template_tokens,
            "query_tokens": self.query_tokens,
            "estimated_hidden_provider_tokens": self.estimated_hidden_provider_tokens,
        }


def count_tokens(text: str, tokenizer) -> int:
    """
    Count tokens in text using the provided tokenizer.
    
    Args:
        text: Text to tokenize
        tokenizer: HuggingFace tokenizer instance
        
    Returns:
        Token count
    """
    if tokenizer is None:
        # Fallback: rough estimate (1 token per 4 chars)
        return len(text) // 4
    
    try:
        tokens = tokenizer.encode(text, add_special_tokens=False)
        return len(tokens)
    except Exception:
        # Fallback on tokenizer error
        return len(text) // 4


def compute_template_tokens(template_content: str, tokenizer) -> int:
    """
    Compute token count of template excluding placeholders.
    
    Removes {query} and {context} placeholders before counting.
    
    Args:
        template_content: Raw template string with placeholders
        tokenizer: HuggingFace tokenizer instance
        
    Returns:
        Token count of template structure only
    """
    # Remove placeholders - these will be counted separately
    template_only = template_content.replace("{query}", "").replace("{context}", "")
    
    # Also remove any other placeholders in case template uses more
    template_only = re.sub(r'\{[a-zA-Z_][a-zA-Z0-9_]*\}', '', template_only)
    
    return count_tokens(template_only, tokenizer)


def load_template_content(template_name: str) -> Optional[str]:
    """
    Load raw template content from templates directory.
    
    Args:
        template_name: Name of template (e.g., "explain")
        
    Returns:
        Template content string or None if not found
    """
    import yaml
    
    # Templates are in src/homllm/generation/templates/
    templates_dir = Path(__file__).parent.parent / "src" / "homllm" / "generation" / "templates"
    template_path = templates_dir / f"{template_name}.yaml"
    
    if not template_path.exists():
        return None
    
    try:
        with open(template_path, "r") as f:
            data = yaml.safe_load(f)
            return data.get("template", "")
    except Exception:
        return None


def compute_token_attribution(
    rendered_prompt: str,
    context_tokens: int,
    query: str,
    template_name: str,
    tokens_in: Optional[int],
    tokenizer,
) -> TokenAttribution:
    """
    Compute token attribution metrics for a query run.
    
    Args:
        rendered_prompt: The final rendered prompt sent to provider
        context_tokens: Token count from ContextArtifact.used_tokens
        query: Raw query string
        template_name: Name of prompt template used
        tokens_in: Provider-reported input tokens (may be None)
        tokenizer: HuggingFace tokenizer instance
        
    Returns:
        TokenAttribution with all computed metrics
    """
    # Count visible prompt tokens
    visible_prompt_tokens = count_tokens(rendered_prompt, tokenizer)
    
    # Count query tokens
    query_tokens = count_tokens(query, tokenizer)
    
    # Load and count template tokens (excluding placeholders)
    template_content = load_template_content(template_name)
    if template_content:
        template_tokens = compute_template_tokens(template_content, tokenizer)
    else:
        # Fallback: estimate from visible - context - query
        template_tokens = max(0, visible_prompt_tokens - context_tokens - query_tokens)
    
    # Compute estimated hidden provider tokens
    estimated_hidden = None
    if tokens_in is not None and tokens_in > 0:
        estimated_hidden = tokens_in - visible_prompt_tokens
        # Could be negative if our counting differs from provider's
        # Keep as-is for diagnostic purposes
    
    return TokenAttribution(
        visible_prompt_tokens=visible_prompt_tokens,
        context_tokens_after_intelligence=context_tokens,
        template_tokens=template_tokens,
        query_tokens=query_tokens,
        estimated_hidden_provider_tokens=estimated_hidden,
    )
