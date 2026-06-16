from dataclasses import dataclass
from pathlib import Path

import pytest

from homllm_v4.contracts.artifacts import ArtifactRef
from homllm_v4.contracts.capability import CapabilityResult
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.telemetry import CapabilityTelemetry
from homllm_v4.serialization.json import to_jsonable


def telemetry(degraded: bool = False) -> CapabilityTelemetry:
    return CapabilityTelemetry(
        started_at="2026-05-09T00:00:00Z",
        ended_at="2026-05-09T00:00:01Z",
        duration_ms=1000,
        input_summary={"query": "hello"},
        output_summary={"count": 1},
        token_usage={},
        model_usage={},
        degraded=degraded,
        degradation_reason="partial vector failure" if degraded else None,
    )


def error() -> CapabilityError:
    return CapabilityError(
        code="adapter_failed",
        message="adapter failed",
        recoverable=False,
        retryable=False,
        details={"stage": "retrieval"},
    )


def test_success_requires_output_and_no_error() -> None:
    result = CapabilityResult(
        capability_name="demo",
        ok=True,
        output={"value": 1},
        error=None,
        telemetry=telemetry(),
        artifacts=(),
    )

    assert result.ok is True
    assert result.output == {"value": 1}


def test_success_without_output_is_invalid() -> None:
    with pytest.raises(ValueError, match="requires output"):
        CapabilityResult(
            capability_name="demo",
            ok=True,
            output=None,
            error=None,
            telemetry=telemetry(),
            artifacts=(),
        )


def test_success_with_error_is_invalid() -> None:
    with pytest.raises(ValueError, match="cannot include error"):
        CapabilityResult(
            capability_name="demo",
            ok=True,
            output={"value": 1},
            error=error(),
            telemetry=telemetry(),
            artifacts=(),
        )


def test_failure_requires_error() -> None:
    with pytest.raises(ValueError, match="requires error"):
        CapabilityResult(
            capability_name="demo",
            ok=False,
            output=None,
            error=None,
            telemetry=telemetry(),
            artifacts=(),
        )


def test_failure_with_output_is_invalid() -> None:
    with pytest.raises(ValueError, match="cannot include output"):
        CapabilityResult(
            capability_name="demo",
            ok=False,
            output={"partial": "data"},
            error=error(),
            telemetry=telemetry(),
            artifacts=(),
        )


def test_degraded_success_is_representable() -> None:
    result = CapabilityResult(
        capability_name="demo",
        ok=True,
        output={"value": 1},
        error=None,
        telemetry=telemetry(degraded=True),
        artifacts=(),
    )

    assert result.ok is True
    assert result.telemetry.degraded is True
    assert result.telemetry.degradation_reason == "partial vector failure"


def test_degraded_telemetry_requires_reason() -> None:
    with pytest.raises(ValueError, match="requires degradation_reason"):
        CapabilityTelemetry(
            started_at="2026-05-09T00:00:00Z",
            ended_at="2026-05-09T00:00:01Z",
            duration_ms=1000,
            degraded=True,
            degradation_reason=None,
        )


def test_degraded_telemetry_rejects_empty_reason() -> None:
    with pytest.raises(ValueError, match="requires degradation_reason"):
        CapabilityTelemetry(
            started_at="2026-05-09T00:00:00Z",
            ended_at="2026-05-09T00:00:01Z",
            duration_ms=1000,
            degraded=True,
            degradation_reason="",
        )


def test_non_degraded_telemetry_rejects_reason() -> None:
    with pytest.raises(ValueError, match="cannot include degradation_reason"):
        CapabilityTelemetry(
            started_at="2026-05-09T00:00:00Z",
            ended_at="2026-05-09T00:00:01Z",
            duration_ms=1000,
            degraded=False,
            degradation_reason="not degraded",
        )


def test_serialization_preserves_nested_contract_fields() -> None:
    artifact = ArtifactRef(
        artifact_type="context",
        path="workspace/.homllm/runs/run-1/context/context.json",
        description="context artifact",
        content_hash=None,
    )
    result = CapabilityResult(
        capability_name="demo",
        ok=True,
        output={"path": Path("a/b"), "items": (1, None, True, 1.5, "x")},
        error=None,
        telemetry=telemetry(),
        artifacts=(artifact,),
    )

    payload = to_jsonable(result)

    assert payload["ok"] is True
    assert payload["output"] == {
        "path": "a/b",
        "items": [1, None, True, 1.5, "x"],
    }
    assert payload["artifacts"][0]["content_hash"] is None


def test_unsupported_serialization_type_raises_value_error() -> None:
    @dataclass(frozen=True)
    class UnsupportedContainer:
        value: object

    with pytest.raises(ValueError, match="serialization_failed"):
        to_jsonable(UnsupportedContainer(value=object()))


def test_serialization_rejects_non_string_dict_keys() -> None:
    with pytest.raises(ValueError, match="serialization_failed"):
        to_jsonable({1: "numeric key", "1": "string key"})
