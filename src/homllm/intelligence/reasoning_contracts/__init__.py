"""
Reasoning Contract Layer (RCL) Module

Phase-2: Converts detected reasoning expectations into explicit,
enforceable reasoning obligations BEFORE generation.

Phase-3A: Enforces contracts by injecting explicit prompt instructions
before model generation (pure declarative constraint projection).

Phase-3B: Enforces answer structure by requiring specific sections
based on reasoning contracts (format enforcement, not content).

Phase-3C: Prompt integrity and completion guards - ensures template
variables are always present and injects stop instructions when
all reasoning obligations are satisfied.

Contracts define what MUST be reasoned, not how.
Enable via --reasoning-contracts CLI flag.

Exports:
- ContractBuilder: Main builder class
- ContractEnforcer: Renders contracts into prompt enforcement text (3A)
- StructureEnforcer: Renders contracts into structure requirements (3B)
- PromptIntegrityGuard: Ensures template variables exist before rendering (3C)
- CompletionGuard: Injects stop instructions when obligations met (3C)
- DeduplicationGuard: Detects duplicate section headers (3C)
- ReasoningContract: Contract data structure
- ReasoningStep: Step type enum
- Constraint: Individual constraint
"""

from homllm.intelligence.reasoning_contracts.interfaces import (
    ReasoningStep,
    ContractSeverity,
    Constraint,
    ReasoningContract,
)

from homllm.intelligence.reasoning_contracts.builder import (
    ContractBuilder,
    create_contract_builder,
)

from homllm.intelligence.reasoning_contracts.collector import (
    ContractCollector,
    create_contract_collector,
)

from homllm.intelligence.reasoning_contracts.enforcer import (
    # Phase-3A
    ContractEnforcer,
    create_contract_enforcer,
    ENFORCEMENT_TEMPLATE,
    # Phase-3B
    StructureEnforcer,
    create_structure_enforcer,
    STRUCTURE_TEMPLATE,
    SECTION_MAPPING,
)

from homllm.intelligence.reasoning_contracts.guards import (
    # Phase-3C
    REQUIRED_TEMPLATE_VARIABLES,
    COMPLETION_GUARD_TEMPLATE,
    SECTION_HEADERS,
    PromptIntegrityGuard,
    create_prompt_integrity_guard,
    CompletionGuard,
    create_completion_guard,
    DeduplicationGuard,
    create_deduplication_guard,
)


__all__ = [
    # Data structures
    "ReasoningStep",
    "ContractSeverity",
    "Constraint",
    "ReasoningContract",
    # Builder
    "ContractBuilder",
    "create_contract_builder",
    # Collector
    "ContractCollector",
    "create_contract_collector",
    # Enforcer (Phase-3A)
    "ContractEnforcer",
    "create_contract_enforcer",
    "ENFORCEMENT_TEMPLATE",
    # Structure Enforcer (Phase-3B)
    "StructureEnforcer",
    "create_structure_enforcer",
    "STRUCTURE_TEMPLATE",
    "SECTION_MAPPING",
    # Guards (Phase-3C)
    "REQUIRED_TEMPLATE_VARIABLES",
    "COMPLETION_GUARD_TEMPLATE",
    "SECTION_HEADERS",
    "PromptIntegrityGuard",
    "create_prompt_integrity_guard",
    "CompletionGuard",
    "create_completion_guard",
    "DeduplicationGuard",
    "create_deduplication_guard",
]
