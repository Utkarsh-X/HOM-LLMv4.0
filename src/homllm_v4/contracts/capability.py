from dataclasses import dataclass, field
from typing import Generic, TypeVar

from homllm_v4.contracts.artifacts import ArtifactRef
from homllm_v4.contracts.errors import CapabilityError
from homllm_v4.contracts.telemetry import CapabilityTelemetry

T = TypeVar("T")


@dataclass(frozen=True)
class CapabilityResult(Generic[T]):
    capability_name: str
    ok: bool
    output: T | None
    error: CapabilityError | None
    telemetry: CapabilityTelemetry
    artifacts: tuple[ArtifactRef, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.ok:
            if self.output is None:
                raise ValueError("successful CapabilityResult requires output")
            if self.error is not None:
                raise ValueError("successful CapabilityResult cannot include error")
        else:
            if self.error is None:
                raise ValueError("failed CapabilityResult requires error")
            if self.output is not None:
                raise ValueError("failed CapabilityResult cannot include output")
