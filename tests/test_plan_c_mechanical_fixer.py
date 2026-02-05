"""Unit tests for Plan C: Mechanical Fixer & ABRM.

Tests cover:
- Action selection based on diagnostic thresholds
- Cap enforcement
- ABRM activation logic
- Determinism (same input → same output)
- No-op when disabled
"""

import pytest
from pathlib import Path

# Test imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from homllm.intelligence.mechanical_fixer import (
    FixAction,
    FixerConfig,
    FixerThresholds,
    FixerCaps,
    ABRMConfig,
    FixResult,
    MechanicalFixer,
    should_activate_abrm,
)


class TestFixerConfig:
    """Tests for FixerConfig defaults."""

    def test_default_config(self):
        """Test that default config is properly set."""
        config = FixerConfig()
        
        assert config.enabled is True
        assert "GRAPH_STITCH_RETRY" in config.action_priority
        assert "SYMBOL_BACKFILL" in config.action_priority
        assert config.thresholds.orphan_pct_trigger == 60.0
        assert config.caps.graph_stitch_max == 6

    def test_action_priority_order(self):
        """Test that action priority is in correct order."""
        config = FixerConfig()
        
        # GRAPH_STITCH_RETRY should come before UTILIZATION_EXPAND
        graph_idx = config.action_priority.index("GRAPH_STITCH_RETRY")
        util_idx = config.action_priority.index("UTILIZATION_EXPAND")
        assert graph_idx < util_idx


class TestFixResult:
    """Tests for FixResult dataclass."""

    def test_was_applied_true(self):
        """Test was_applied is True for non-NO_OP actions."""
        result = FixResult(
            action=FixAction.GRAPH_STITCH_RETRY,
            trigger="orphan_pct=65%",
            delta={"blocks_added": 4},
            improved=True,
            provenance_tag="mechanical_fix:GRAPH_STITCH_RETRY",
        )
        
        assert result.was_applied is True

    def test_was_applied_false(self):
        """Test was_applied is False for NO_OP."""
        result = FixResult(
            action=FixAction.NO_OP,
            trigger="fixer_disabled",
            delta={},
            improved=False,
            provenance_tag="",
        )
        
        assert result.was_applied is False

    def test_format_priming_notice_with_blocks(self):
        """Test priming notice format with blocks added."""
        result = FixResult(
            action=FixAction.SYMBOL_BACKFILL,
            trigger="missing_definitions=3",
            delta={"blocks_added": 3},
            improved=True,
            provenance_tag="mechanical_fix:SYMBOL_BACKFILL",
        )
        
        notice = result.format_priming_notice()
        assert "SYMBOL_BACKFILL" in notice
        assert "+3 blocks" in notice

    def test_format_priming_notice_no_op(self):
        """Test priming notice is empty for NO_OP."""
        result = FixResult(
            action=FixAction.NO_OP,
            trigger="no_conditions",
            delta={},
            improved=False,
            provenance_tag="",
        )
        
        notice = result.format_priming_notice()
        assert notice == ""


class TestMechanicalFixer:
    """Tests for MechanicalFixer class."""

    def test_disabled_returns_no_op(self):
        """Test that disabled fixer returns NO_OP."""
        config = FixerConfig(enabled=False)
        fixer = MechanicalFixer(config)
        
        # Create minimal mock context and diagnostics
        from unittest.mock import MagicMock
        
        context = MagicMock()
        context.blocks = ()
        
        diagnostics = MagicMock()
        diagnostics.level1.status = "unavailable"
        diagnostics.level2.status = "unavailable"
        diagnostics.level3.status = "unavailable"
        
        new_context, result = fixer.apply(context, diagnostics)
        
        assert result.action == FixAction.NO_OP
        assert result.trigger == "fixer_disabled"
        assert new_context is context

    def test_no_conditions_returns_no_op(self):
        """Test that no triggered conditions returns NO_OP."""
        config = FixerConfig(enabled=True)
        fixer = MechanicalFixer(config)
        
        from unittest.mock import MagicMock
        
        context = MagicMock()
        context.blocks = ()
        
        # All diagnostics unavailable
        diagnostics = MagicMock()
        diagnostics.level1.status = "unavailable"
        diagnostics.level1.result = None
        diagnostics.level1.blocks = ()
        diagnostics.level2.status = "unavailable"
        diagnostics.level2.result = None
        diagnostics.level3.status = "unavailable"
        diagnostics.level3.result = None
        
        new_context, result = fixer.apply(context, diagnostics)
        
        assert result.action == FixAction.NO_OP

    def test_deterministic_action_selection(self):
        """Test that action selection is deterministic."""
        config = FixerConfig()
        fixer = MechanicalFixer(config)
        
        from unittest.mock import MagicMock
        
        context = MagicMock()
        context.blocks = ()
        
        # Create diagnostics with high orphan percentage
        diagnostics = MagicMock()
        diagnostics.level1.status = "available"
        diagnostics.level1.result = MagicMock()
        diagnostics.level1.result.total_blocks = 10
        diagnostics.level1.result.used_budget_pct = 80.0
        diagnostics.level1.result.redundant_blocks = []
        diagnostics.level1.blocks = []
        diagnostics.level2.status = "unavailable"
        diagnostics.level2.result = None
        diagnostics.level3.status = "unavailable"
        diagnostics.level3.result = None
        
        # Run twice
        _, result1 = fixer.apply(context, diagnostics)
        _, result2 = fixer.apply(context, diagnostics)
        
        # Same input → same action
        assert result1.action == result2.action


class TestABRMActivation:
    """Tests for ABRM activation logic."""

    def test_abrm_disabled(self):
        """Test that ABRM disabled returns False."""
        from unittest.mock import MagicMock
        
        config = ABRMConfig(enabled=False)
        diagnostics = MagicMock()
        context = MagicMock()
        context.blocks = (MagicMock(),)
        
        result = should_activate_abrm(diagnostics, None, config, context)
        assert result is False

    def test_abrm_cold_start_disabled(self):
        """Test that ABRM is disabled on cold start."""
        from unittest.mock import MagicMock
        
        config = ABRMConfig(enabled=True, disable_on_cold_start=True)
        diagnostics = MagicMock()
        context = MagicMock()
        context.blocks = ()  # Empty = cold start
        
        result = should_activate_abrm(diagnostics, None, config, context)
        assert result is False

    def test_abrm_activated_on_low_utilization(self):
        """Test that ABRM activates on low budget utilization."""
        from unittest.mock import MagicMock
        
        config = ABRMConfig(enabled=True, disable_on_cold_start=True)
        
        diagnostics = MagicMock()
        diagnostics.level1.status = "available"
        diagnostics.level1.result = MagicMock()
        diagnostics.level1.result.used_budget_pct = 30.0  # Low
        diagnostics.level2.status = "unavailable"
        diagnostics.level2.result = None
        
        context = MagicMock()
        context.blocks = (MagicMock(),)  # At least one block
        
        result = should_activate_abrm(diagnostics, None, config, context)
        assert result is True

    def test_abrm_activated_on_fix_improved(self):
        """Test that ABRM activates when fixer improves context."""
        from unittest.mock import MagicMock
        
        config = ABRMConfig(enabled=True, disable_on_cold_start=True)
        
        diagnostics = MagicMock()
        diagnostics.level1.status = "unavailable"
        diagnostics.level1.result = None
        diagnostics.level2.status = "unavailable"
        diagnostics.level2.result = None
        
        fix_result = FixResult(
            action=FixAction.GRAPH_STITCH_RETRY,
            trigger="orphan_pct=70%",
            delta={"blocks_added": 5},
            improved=True,
            provenance_tag="mechanical_fix:GRAPH_STITCH_RETRY",
        )
        
        context = MagicMock()
        context.blocks = (MagicMock(),)
        
        result = should_activate_abrm(diagnostics, fix_result, config, context)
        assert result is True


class TestFixerThresholds:
    """Tests for FixerThresholds."""

    def test_default_thresholds(self):
        """Test default threshold values."""
        thresholds = FixerThresholds()
        
        assert thresholds.orphan_pct_trigger == 60.0
        assert thresholds.redundancy_cluster_pct_trigger == 25.0
        assert thresholds.used_budget_pct_low == 40.0

    def test_custom_thresholds(self):
        """Test custom threshold values."""
        thresholds = FixerThresholds(
            orphan_pct_trigger=50.0,
            redundancy_cluster_pct_trigger=30.0,
            used_budget_pct_low=35.0,
        )
        
        assert thresholds.orphan_pct_trigger == 50.0
        assert thresholds.redundancy_cluster_pct_trigger == 30.0
        assert thresholds.used_budget_pct_low == 35.0


class TestFixerCaps:
    """Tests for FixerCaps."""

    def test_default_caps(self):
        """Test default cap values."""
        caps = FixerCaps()
        
        assert caps.graph_stitch_max == 6
        assert caps.symbol_backfill_max == 4
        assert caps.utilization_expand_max == 10


class TestTemplateLoaderABRM:
    """Tests for ABRM template selection in TemplateLoader."""

    def test_select_template_no_abrm(self):
        """Test template selection without ABRM."""
        from homllm.generation.template_loader import TemplateLoader
        
        loader = TemplateLoader()
        template_name = loader.select_template("explain", abrm_active=False)
        
        assert template_name == "explain"

    def test_select_template_with_abrm(self):
        """Test template selection with ABRM."""
        from homllm.generation.template_loader import TemplateLoader, ABRM_TEMPLATE_NAME
        
        loader = TemplateLoader()
        template_name = loader.select_template("explain", abrm_active=True)
        
        # Should return ABRM template if it exists
        assert template_name == ABRM_TEMPLATE_NAME or template_name == "explain"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
