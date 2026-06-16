# HOM-LLM v4 Architecture Workspace

This directory is for architecture discovery and design only.

No v4 implementation should begin until the architecture documents answer:

- What parts of v3 are reusable as stable services?
- What parts of v3 are useful only as references?
- What parts of v3 should not be carried forward?
- What are the typed tool contracts for read, retrieve, write, execute, verify, and patch operations?
- What are the stop rules, permission boundaries, and verification gates?
- What must be proven by evaluation before v4 becomes a product track?

## Working Rule

HOM-LLM v4 should not be a rushed rewrite. It should be a clean architecture that preserves the hard-won retrieval, ranking, context, diagnostics, and evaluation lessons from v3 while removing the single-pass/read-only assumptions that constrain the current design.

## Document Order

1. `01-current-system-asset-map.md`
   - Map v3 components into reuse, wrap, rewrite, or discard decisions.

2. `02-v4-first-principles-architecture.md`
   - Define the target system from first principles.

3. `03-tool-and-service-contracts.md`
   - Specify typed tools, permissions, telemetry, and failure modes.

4. `04-agent-loop-and-memory-design.md`
   - Specify multi-pass planning, working memory, stop rules, and state transitions.

5. `05-write-execute-verify-design.md`
   - Specify safe patching, execution, verification, rollback, and completion gates.

6. `06-migration-and-validation-plan.md`
   - Specify how v4 is built beside v3, evaluated, and promoted.

7. `07-milestone-1-implementation-spec.md`
   - Narrow Milestone 1 into concrete package, contract, adapter, artifact, and test requirements.

8. `08-milestone-1-4-implementation-audit.md`
   - Audit the implemented v4 foundation against Milestone 1-4 exit criteria and record remaining gaps.
