"""Unit tests for RET-IMP-08 single budget authority parsing."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from homllm.common.config import Config


def _load_default_dict() -> dict:
    path = Path("configs/default.yaml")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_retrieval_budget_authority_uses_context_budget_values():
    cfg = Config.from_file(Path("configs/default.yaml"))
    retrieval = cfg.get_retrieval_config()

    assert retrieval.context_budget == cfg.context["max_tokens"]
    assert retrieval.budget_reserve == cfg.context["generation_reserve_tokens"]


def test_retrieval_budget_authority_reserve_falls_back_to_context_default_rule():
    data = _load_default_dict()
    data["context"]["max_tokens"] = 3500
    data["context"].pop("generation_reserve_tokens", None)

    cfg = Config(**data)
    retrieval = cfg.get_retrieval_config()
    assert retrieval.context_budget == 3500
    assert retrieval.budget_reserve == 700  # 20% of 3500


def test_retrieval_budget_enabled_toggle_remains_local():
    data = _load_default_dict()
    data["retrieval"]["budget"] = {"enabled": False}

    cfg = Config(**data)
    retrieval = cfg.get_retrieval_config()
    assert retrieval.budget_aware_selection is False
    assert retrieval.context_budget == cfg.context["max_tokens"]


@pytest.mark.parametrize(
    "budget_cfg",
    [
        {"context_budget": 5000},
        {"reserve": 1000},
        {"enabled": True, "context_budget": 5000, "reserve": 1000},
    ],
)
def test_retrieval_budget_dual_authority_hard_fails(budget_cfg: dict):
    data = deepcopy(_load_default_dict())
    data["retrieval"]["budget"] = budget_cfg

    cfg = Config(**data)
    with pytest.raises(ValueError, match="Dual budget authority detected"):
        cfg.get_retrieval_config()
