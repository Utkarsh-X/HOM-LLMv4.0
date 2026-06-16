from dataclasses import dataclass, field


@dataclass(frozen=True)
class CapabilityTelemetry:
    started_at: str
    ended_at: str
    duration_ms: int
    input_summary: dict[str, object] = field(default_factory=dict)
    output_summary: dict[str, object] = field(default_factory=dict)
    token_usage: dict[str, int] = field(default_factory=dict)
    model_usage: dict[str, object] = field(default_factory=dict)
    degraded: bool = False
    degradation_reason: str | None = None

    def __post_init__(self) -> None:
        if self.degraded:
            if not self.degradation_reason:
                raise ValueError("degraded CapabilityTelemetry requires degradation_reason")
        elif self.degradation_reason is not None:
            raise ValueError("non-degraded CapabilityTelemetry cannot include degradation_reason")
