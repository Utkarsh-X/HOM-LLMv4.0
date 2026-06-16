from dataclasses import dataclass, field


@dataclass(frozen=True)
class CapabilityError:
    code: str
    message: str
    recoverable: bool
    retryable: bool
    details: dict[str, object] = field(default_factory=dict)
