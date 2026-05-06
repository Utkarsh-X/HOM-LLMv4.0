# Read-Only Orchestration V1 Validation

## Purpose

This runbook validates that read-only agentic orchestration is clean, measured, and non-regressing before HOM-LLM moves toward execution or patch-capable modes.

## Unit Verification

Run:

```powershell
python -m pytest tests/unit/test_agentic_config.py tests/unit/test_agent_router.py tests/unit/test_agent_orchestrator.py -q
```

Expected:

- agentic config parsing tests pass
- all router tests pass
- all orchestrator helper tests pass
- no provider API keys are required

## Import Smoke Test

Run:

```powershell
python -c "import runtime.run_query; import homllm.agent.router; import homllm.agent.orchestrator; print('imports ok')"
```

Expected:

```text
imports ok
```

Environment note:

If this fails with `ModuleNotFoundError: No module named 'torch'`, classify it as the pre-existing runtime import dependency through `QwenEmbedder`, not an agentic wiring failure. In that case, also run:

```powershell
$env:PYTHONPATH='src'; python -c "import homllm.agent.router; import homllm.agent.orchestrator; print('agent imports ok')"
```

Expected:

```text
agent imports ok
```

## Existing Canary Compatibility

Existing canary configs that set `agentic.enabled: true` and `agentic.default_mode: read_only_agentic` but leave `agentic.router_enabled: false` should keep routing all selected queries through read-only agentic mode.

Compatibility condition:

- router disabled means `router_disabled_default_mode`
- no old canary silently changes from read-only agentic to single-pass

## Selective Router Probe

Create a temporary config variant that sets:

```yaml
agentic:
  enabled: true
  default_mode: read_only_agentic
  router_enabled: true
  default_permission_mode: read_only
  loop:
    read_only_max_iterations: 3
    max_repeated_signature: 2
    max_command_failures: 0
```

Expected routing:

- short explain/search tasks stay single-pass
- debug, refactor, implement, and complex explain tasks use read-only agentic mode

## Known Regression Classes

These query classes require special attention before promotion:

- partial failure and at-least-once semantics
- optimizer rule synthesis with timing and plan caching
- stress test outcome synthesis

Observed failure pattern:

The read-only agentic path can become more generic or less synthesized than the baseline. The next fix should improve sufficiency, synthesis, and verification gates rather than adding broader autonomy.

## Promotion Gate

Do not move to execution mode until:

- selected hard tasks improve or match baseline
- simple explain/search tasks do not regress
- agentic trace artifacts are written for read-only runs
- route decisions are visible in telemetry
- the three known regression classes are either fixed or documented with an explicit acceptance decision
