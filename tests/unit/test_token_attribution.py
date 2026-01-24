"""
Unit tests for token attribution module.

Tests:
1. Token counting with and without tokenizer
2. Template token computation excludes placeholders
3. TokenAttribution dataclass fields
4. Compute function handles missing provider tokens
"""

import pytest
from unittest.mock import Mock


def test_token_attribution_imports_succeed():
    """Verify token attribution module imports work correctly."""
    from runtime.token_attribution import (
        TokenAttribution,
        count_tokens,
        compute_template_tokens,
        compute_token_attribution,
    )
    
    assert TokenAttribution is not None
    assert count_tokens is not None
    assert compute_template_tokens is not None
    assert compute_token_attribution is not None


def test_token_attribution_dataclass_fields():
    """Verify TokenAttribution has all required fields."""
    from runtime.token_attribution import TokenAttribution
    
    attribution = TokenAttribution(
        visible_prompt_tokens=1000,
        context_tokens_after_intelligence=800,
        template_tokens=50,
        query_tokens=20,
        estimated_hidden_provider_tokens=100,
    )
    
    assert attribution.visible_prompt_tokens == 1000
    assert attribution.context_tokens_after_intelligence == 800
    assert attribution.template_tokens == 50
    assert attribution.query_tokens == 20
    assert attribution.estimated_hidden_provider_tokens == 100


def test_token_attribution_to_dict():
    """Verify TokenAttribution.to_dict returns all fields."""
    from runtime.token_attribution import TokenAttribution
    
    attribution = TokenAttribution(
        visible_prompt_tokens=100,
        context_tokens_after_intelligence=80,
        template_tokens=10,
        query_tokens=5,
        estimated_hidden_provider_tokens=10,
    )
    
    result = attribution.to_dict()
    
    assert "visible_prompt_tokens" in result
    assert "context_tokens_after_intelligence" in result
    assert "template_tokens" in result
    assert "query_tokens" in result
    assert "estimated_hidden_provider_tokens" in result


def test_count_tokens_without_tokenizer():
    """Verify count_tokens uses fallback when tokenizer is None."""
    from runtime.token_attribution import count_tokens
    
    text = "Hello world"  # 11 chars -> ~2 tokens (11 // 4)
    result = count_tokens(text, tokenizer=None)
    
    assert result == len(text) // 4


def test_count_tokens_with_tokenizer():
    """Verify count_tokens uses tokenizer when available."""
    from runtime.token_attribution import count_tokens
    
    mock_tokenizer = Mock()
    mock_tokenizer.encode.return_value = [1, 2, 3, 4, 5]  # 5 tokens
    
    result = count_tokens("test text", tokenizer=mock_tokenizer)
    
    assert result == 5
    mock_tokenizer.encode.assert_called_once_with("test text", add_special_tokens=False)


def test_compute_template_tokens_excludes_placeholders():
    """Verify template token counting excludes {query} and {context}."""
    from runtime.token_attribution import compute_template_tokens
    
    template = "Hello {query}, here is {context}. Instructions follow."
    # After removing placeholders: "Hello , here is . Instructions follow."
    
    mock_tokenizer = Mock()
    mock_tokenizer.encode.return_value = [1, 2, 3, 4, 5, 6]  # 6 tokens for template structure
    
    result = compute_template_tokens(template, mock_tokenizer)
    
    assert result == 6
    # Verify the call was made without placeholders
    call_args = mock_tokenizer.encode.call_args[0][0]
    assert "{query}" not in call_args
    assert "{context}" not in call_args


def test_hidden_tokens_none_when_no_provider_report():
    """Verify estimated_hidden_provider_tokens is None when tokens_in unavailable."""
    from runtime.token_attribution import compute_token_attribution
    
    mock_tokenizer = Mock()
    mock_tokenizer.encode.return_value = [1, 2, 3]  # 3 tokens
    
    attribution = compute_token_attribution(
        rendered_prompt="test prompt",
        context_tokens=10,
        query="test",
        template_name="nonexistent",
        tokens_in=None,  # Provider didn't report
        tokenizer=mock_tokenizer,
    )
    
    assert attribution.estimated_hidden_provider_tokens is None


def test_hidden_tokens_computed_when_provider_reports():
    """Verify estimated_hidden_provider_tokens is computed when tokens_in available."""
    from runtime.token_attribution import compute_token_attribution
    
    mock_tokenizer = Mock()
    mock_tokenizer.encode.return_value = [1, 2, 3, 4, 5]  # 5 tokens
    
    attribution = compute_token_attribution(
        rendered_prompt="test prompt",
        context_tokens=10,
        query="test",
        template_name="nonexistent",
        tokens_in=15,  # Provider reports 15 tokens
        tokenizer=mock_tokenizer,
    )
    
    # estimated_hidden = tokens_in - visible_prompt_tokens = 15 - 5 = 10
    assert attribution.estimated_hidden_provider_tokens == 10


def test_token_attribution_frozen():
    """Verify TokenAttribution is immutable."""
    from runtime.token_attribution import TokenAttribution
    
    attribution = TokenAttribution(
        visible_prompt_tokens=100,
        context_tokens_after_intelligence=80,
        template_tokens=10,
        query_tokens=5,
        estimated_hidden_provider_tokens=None,
    )
    
    with pytest.raises(Exception):
        attribution.visible_prompt_tokens = 200
