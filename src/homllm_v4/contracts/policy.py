from dataclasses import dataclass, field


@dataclass(frozen=True)
class CapabilityPolicy:
    permission_profile: str
    approval_policy: str
    sandbox_policy: str
    allowed_tools: tuple[str, ...]
    blocked_tools: tuple[str, ...]
    verification_requirements: tuple[str, ...] = field(default_factory=tuple)
    budget_caps: dict[str, int] = field(default_factory=dict)
    escalation_rules: tuple[str, ...] = field(default_factory=tuple)


def read_only_milestone1_policy() -> CapabilityPolicy:
    return CapabilityPolicy(
        permission_profile="ReadOnly",
        approval_policy="never",
        sandbox_policy="read_only",
        allowed_tools=(
            "index.validate",
            "evidence.retrieve",
            "evidence.rank",
            "context.build",
            "file.read",
        ),
        blocked_tools=("command.run", "patch.apply", "tests.run"),
        verification_requirements=(),
        budget_caps={
            "retrieval_calls": 1,
            "ranking_calls": 1,
            "context_calls": 1,
            "direct_reads": 3,
            "llm_calls": 0,
        },
        escalation_rules=(),
    )
