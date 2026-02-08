"""Fixer configuration parser.

Parses mechanical fixer and ABRM configuration from YAML config.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homllm.intelligence.mechanical_fixer import (
    ABRMConfig,
    FixerCaps,
    FixerConfig,
    FixerThresholds,
)

if TYPE_CHECKING:
    from homllm.common.config import Config

logger = logging.getLogger(__name__)


def _extract_intelligence_cfg(config: "Config") -> dict[str, Any]:
    """
    Extract intelligence configuration from the runtime Config object.

    Supports current `Config` shape (`config.intelligence`) and a legacy
    fallback (`config.cfg["intelligence"]`) used by older call sites.
    """
    intelligence_cfg = getattr(config, "intelligence", None)
    if isinstance(intelligence_cfg, dict):
        return intelligence_cfg

    legacy_cfg = getattr(config, "cfg", None)
    if isinstance(legacy_cfg, dict):
        legacy_intelligence = legacy_cfg.get("intelligence", {})
        if isinstance(legacy_intelligence, dict):
            return legacy_intelligence

    return {}


def get_fixer_config(config: "Config") -> FixerConfig:
    """
    Parse FixerConfig from Config object.
    
    Args:
        config: Main configuration object
        
    Returns:
        FixerConfig with parsed or default values
    """
    intelligence_cfg = _extract_intelligence_cfg(config)
    
    # Check if fixer is enabled
    enabled = intelligence_cfg.get("mechanical_fixer_enabled", True)
    
    # Parse action priority
    action_priority = intelligence_cfg.get("action_priority", [
        "GRAPH_STITCH_RETRY",
        "SYMBOL_BACKFILL",
        "SEMANTIC_DEDUP_FORCE",
        "UTILIZATION_EXPAND",
    ])
    
    # Parse thresholds
    thresholds_cfg = intelligence_cfg.get("thresholds", {})
    thresholds = FixerThresholds(
        orphan_pct_trigger=thresholds_cfg.get("orphan_pct_trigger", 60.0),
        redundancy_cluster_pct_trigger=thresholds_cfg.get("redundancy_cluster_pct_trigger", 25.0),
        used_budget_pct_low=thresholds_cfg.get("used_budget_pct_low", 40.0),
    )
    
    # Parse caps
    caps_cfg = intelligence_cfg.get("caps", {})
    caps = FixerCaps(
        graph_stitch_max=caps_cfg.get("graph_stitch_max", 6),
        symbol_backfill_max=caps_cfg.get("symbol_backfill_max", 4),
        utilization_expand_max=caps_cfg.get("utilization_expand_max", 10),
    )
    
    return FixerConfig(
        enabled=enabled,
        action_priority=action_priority,
        thresholds=thresholds,
        caps=caps,
    )


def get_abrm_config(config: "Config") -> ABRMConfig:
    """
    Parse ABRMConfig from Config object.
    
    Args:
        config: Main configuration object
        
    Returns:
        ABRMConfig with parsed or default values
    """
    intelligence_cfg = _extract_intelligence_cfg(config)
    
    enabled = intelligence_cfg.get("abrm_enabled", True)
    disable_on_cold_start = intelligence_cfg.get("abrm_disable_on_cold_start", True)
    
    return ABRMConfig(
        enabled=enabled,
        disable_on_cold_start=disable_on_cold_start,
    )


__all__ = [
    "get_fixer_config",
    "get_abrm_config",
]
