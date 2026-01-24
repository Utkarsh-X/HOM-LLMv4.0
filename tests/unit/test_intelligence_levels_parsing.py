"""
Unit tests for intelligence levels parsing.

Tests:
1. Parsing 'none' disables all levels
2. Parsing 'l1' enables only level 1
3. Parsing 'l1,l2' enables levels 1 and 2
4. Parsing 'l1,l2,l3' enables all levels
5. Invalid spec raises ValueError
"""

import pytest


def test_parse_intelligence_levels_none():
    """Verify 'none' disables all levels."""
    from runtime.run_query import parse_intelligence_levels
    
    enabled, l1, l2, l3 = parse_intelligence_levels("none")
    
    assert enabled is False
    assert l1 is False
    assert l2 is False
    assert l3 is False


def test_parse_intelligence_levels_l1_only():
    """Verify 'l1' enables only level 1."""
    from runtime.run_query import parse_intelligence_levels
    
    enabled, l1, l2, l3 = parse_intelligence_levels("l1")
    
    assert enabled is True
    assert l1 is True
    assert l2 is False
    assert l3 is False


def test_parse_intelligence_levels_l1_l2():
    """Verify 'l1,l2' enables levels 1 and 2."""
    from runtime.run_query import parse_intelligence_levels
    
    enabled, l1, l2, l3 = parse_intelligence_levels("l1,l2")
    
    assert enabled is True
    assert l1 is True
    assert l2 is True
    assert l3 is False


def test_parse_intelligence_levels_full():
    """Verify 'l1,l2,l3' enables all levels."""
    from runtime.run_query import parse_intelligence_levels
    
    enabled, l1, l2, l3 = parse_intelligence_levels("l1,l2,l3")
    
    assert enabled is True
    assert l1 is True
    assert l2 is True
    assert l3 is True


def test_parse_intelligence_levels_case_insensitive():
    """Verify parsing is case insensitive."""
    from runtime.run_query import parse_intelligence_levels
    
    enabled1, _, _, _ = parse_intelligence_levels("NONE")
    enabled2, l1, _, _ = parse_intelligence_levels("L1")
    enabled3, _, l2, _ = parse_intelligence_levels("L1,L2")
    
    assert enabled1 is False
    assert enabled2 is True and l1 is True
    assert enabled3 is True and l2 is True


def test_parse_intelligence_levels_with_whitespace():
    """Verify parsing handles whitespace."""
    from runtime.run_query import parse_intelligence_levels
    
    enabled, l1, l2, l3 = parse_intelligence_levels("  l1,l2  ")
    
    assert enabled is True
    assert l1 is True
    assert l2 is True
    assert l3 is False


def test_parse_intelligence_levels_invalid_raises():
    """Verify invalid spec raises ValueError."""
    from runtime.run_query import parse_intelligence_levels
    
    with pytest.raises(ValueError) as exc_info:
        parse_intelligence_levels("invalid")
    
    assert "Invalid intelligence-levels" in str(exc_info.value)


def test_parse_intelligence_levels_partial_raises():
    """Verify partial/malformed specs raise ValueError."""
    from runtime.run_query import parse_intelligence_levels
    
    with pytest.raises(ValueError):
        parse_intelligence_levels("l2")  # Must start from l1
    
    with pytest.raises(ValueError):
        parse_intelligence_levels("l1,l3")  # Can't skip l2
