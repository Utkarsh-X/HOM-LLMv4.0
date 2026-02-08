"""Unit tests for Plan C fixer configuration parsing."""

from dataclasses import dataclass

from homllm.intelligence.fixer_config import get_abrm_config, get_fixer_config


@dataclass
class _ConfigCurrentShape:
    intelligence: dict


@dataclass
class _ConfigLegacyShape:
    cfg: dict


def test_get_fixer_config_reads_current_config_shape():
    config = _ConfigCurrentShape(
        intelligence={
            "mechanical_fixer_enabled": True,
            "action_priority": ["UTILIZATION_EXPAND", "GRAPH_STITCH_RETRY"],
            "thresholds": {
                "orphan_pct_trigger": 55.0,
                "redundancy_cluster_pct_trigger": 30.0,
                "used_budget_pct_low": 35.0,
            },
            "caps": {
                "graph_stitch_max": 7,
                "symbol_backfill_max": 5,
                "utilization_expand_max": 11,
            },
        }
    )

    fixer = get_fixer_config(config)
    assert fixer.enabled is True
    assert fixer.action_priority[0] == "UTILIZATION_EXPAND"
    assert fixer.thresholds.orphan_pct_trigger == 55.0
    assert fixer.caps.graph_stitch_max == 7


def test_get_abrm_config_reads_current_config_shape():
    config = _ConfigCurrentShape(
        intelligence={
            "abrm_enabled": False,
            "abrm_disable_on_cold_start": False,
        }
    )

    abrm = get_abrm_config(config)
    assert abrm.enabled is False
    assert abrm.disable_on_cold_start is False


def test_get_fixer_config_legacy_cfg_fallback():
    config = _ConfigLegacyShape(
        cfg={
            "intelligence": {
                "mechanical_fixer_enabled": False,
                "caps": {"graph_stitch_max": 9},
            }
        }
    )

    fixer = get_fixer_config(config)
    assert fixer.enabled is False
    assert fixer.caps.graph_stitch_max == 9
