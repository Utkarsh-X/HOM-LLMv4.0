"""Unit tests for agentic configuration parsing."""

from homllm.common.config import AgenticConfig, AgenticLoopConfig, Config


def _base_config(agentic: dict | None = None) -> Config:
    return Config(
        indexer={},
        retrieval={},
        ranking={},
        context={},
        intelligence={},
        agentic=agentic or {},
        generation={},
        evaluation={},
    )


def test_get_agentic_config_defaults_to_disabled_single_pass():
    agentic = _base_config().get_agentic_config()

    assert isinstance(agentic, AgenticConfig)
    assert isinstance(agentic.loop, AgenticLoopConfig)
    assert agentic.enabled is False
    assert agentic.default_mode == "single_pass"
    assert agentic.router_enabled is False
    assert agentic.default_permission_mode == "read_only"
    assert agentic.loop.read_only_max_iterations == 4
    assert agentic.loop.max_repeated_signature == 2
    assert agentic.loop.max_command_failures == 2


def test_get_agentic_config_reads_overrides():
    agentic = _base_config(
        {
            "enabled": True,
            "default_mode": "read_only_agentic",
            "router_enabled": True,
            "subagents_enabled": True,
            "verification_gates_enabled": True,
            "execution_enabled": True,
            "patch_enabled": True,
            "default_permission_mode": "workspace_write",
            "loop": {
                "single_pass_max_iterations": 1,
                "read_only_max_iterations": 3,
                "verification_max_iterations": 5,
                "execution_max_iterations": 6,
                "patch_max_iterations": 2,
                "max_repeated_signature": 4,
                "max_command_failures": 1,
            },
        }
    ).get_agentic_config()

    assert agentic.enabled is True
    assert agentic.default_mode == "read_only_agentic"
    assert agentic.router_enabled is True
    assert agentic.subagents_enabled is True
    assert agentic.verification_gates_enabled is True
    assert agentic.execution_enabled is True
    assert agentic.patch_enabled is True
    assert agentic.default_permission_mode == "workspace_write"
    assert agentic.loop.single_pass_max_iterations == 1
    assert agentic.loop.read_only_max_iterations == 3
    assert agentic.loop.verification_max_iterations == 5
    assert agentic.loop.execution_max_iterations == 6
    assert agentic.loop.patch_max_iterations == 2
    assert agentic.loop.max_repeated_signature == 4
    assert agentic.loop.max_command_failures == 1
