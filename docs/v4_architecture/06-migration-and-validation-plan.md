# HOM-LLM v4 Migration and Validation Plan

Date: 2026-05-09

## Purpose

This document defines how HOM-LLM v4 should be built beside v3, validated milestone by milestone, and promoted only when evidence supports the move.

The goal is to avoid two failure modes:

1. Rushing into a rewrite and losing the hard-won v3 retrieval/ranking/context capabilities.
2. Continuing to patch v3 until the architecture becomes too constrained to support a real coding agent.

v4 should be treated as a disciplined product/research track: architecture first, service boundaries second, evaluation third, write capability only after safety and verification are ready.

## Strategic Goal

Build a token-efficient, evidence-first coding agent that uses HOM-LLM retrieval, ranking, and context assembly as its core advantage, then adds bounded planning, patching, execution, and verification only where needed.

The validation question is:

> Can a RAG-first coding agent solve repository tasks with fewer tokens, less wandering, stronger grounding, and safer write/execute behavior than generic agentic workflows?

This does not require claiming to beat every coding agent. It requires proving that HOM-LLM has a defensible advantage in specific task classes.

## Migration Principles

### 1. Build Beside v3

v4 should not replace v3 in-place.

Reasons:
- v3 remains the working baseline.
- v3 provides reusable services and evaluation data.
- v4 can fail or pivot without destroying the current system.
- side-by-side comparison becomes possible.

Recommended location:
- implementation decision deferred until planning
- likely options:
  - `src/homllm_v4/`
  - `src/homllm/v4/`

Initial recommendation:
- use a separate v4 package namespace first
- wrap v3 services behind interfaces
- avoid changing v3 runtime behavior during early milestones

### 2. Wrap Before Rewrite

The first implementation should wrap v3 capabilities, not rebuild them.

Wrap:
- indexing
- retrieval
- ranking
- context packing
- provider abstraction where useful
- evaluation harness

Do not carry forward:
- single-pass runtime coupling
- prompt-as-control architecture
- silent fallback behavior
- config knobs not consumed by runtime
- answer generation as the only endpoint

### 3. Prove Boundaries Before Adding Power

v4 should first prove:
- typed contracts
- run ledger
- evidence memory
- sufficiency decisions
- grounded response composition

Only after that should it add:
- command execution
- patch application
- repair loops
- rollback

### 4. Evaluation Decides Promotion

No milestone is promoted because the design feels elegant.

Each milestone needs:
- objective exit criteria
- regression checks
- telemetry
- known failure cases
- comparison against v3 and selected baselines where possible

### 5. Product Track Is Earned

v4 should preserve the possibility of a production-grade product, but product work should not begin before core behavior is proven.

Product-track promotion requires evidence across:
- quality
- cost
- latency
- safety
- repeatability
- setup complexity
- user trust

## Migration Architecture

```text
Current v3 System
  -> v3 Service Adapters
  -> v4 Typed Contracts
  -> v4 Runtime State Machine
  -> v4 Evidence/Tool/Verification Memory
  -> v4 Evaluation Ledger
  -> v4 Product Candidate
```

The migration should create a clean seam between "existing capability" and "new orchestration."

## v3 Assets To Preserve

### Indexing

Preserve:
- repository scanning
- chunking
- entity extraction
- graph artifacts
- vector/BM25 artifact creation

Validation needed:
- manifest correctness
- schema versioning
- ignored file reporting
- vector dimension checks
- index staleness detection

### Retrieval

Preserve:
- BM25 retrieval
- vector retrieval
- hybrid fusion
- graph/context expansion
- retrieval diagnostics
- broad/narrow retrieval policies as concepts

Validation needed:
- channel contribution telemetry
- vector failure visibility
- no silent fallback to sparse-only unless marked degraded
- query policy actually affects retrieval behavior

### Ranking

Preserve:
- feature-based ranking
- reranker integration
- ranking diagnostics
- fallback when reranker unavailable

Validation needed:
- GPU/device selection visible
- latency budgets
- fallback status explicit
- ranking explanation usable for debugging

### Context Assembly

Preserve:
- token budgeting
- block selection
- deduplication
- context quality traces
- dropped-evidence reporting

Validation needed:
- purpose-specific context modes
- answer vs planning vs patch context separation
- stable citation/evidence ids

### Evaluation Harness

Preserve:
- run experiment flow
- judge-based comparison
- baseline comparison scripts
- telemetry-print mode
- manual runbooks

Validation needed:
- partial judge results clearly marked incomplete
- nested metric comparison reliable
- token/latency/cost captured across runs
- judge provider instability handled explicitly

## v3 Constraints To Avoid

Do not recreate:
- one large runtime function
- one-shot answer path as the center of the system
- read-only assumptions inside state model
- generation-first orchestration
- tool behavior controlled mostly by prompts
- retry and fallback behavior hidden from telemetry
- evaluation that cannot represent incomplete/partial results

These are not moral failures of v3; they are the architectural ceiling v4 exists to remove.

## Milestone 0: Architecture Lock

Goal:
- Finish and review the architecture documents before implementation begins.

Artifacts:
- `01-current-system-asset-map.md`
- `02-v4-first-principles-architecture.md`
- `03-tool-and-service-contracts.md`
- `04-agent-loop-and-memory-design.md`
- `05-write-execute-verify-design.md`
- `06-migration-and-validation-plan.md`

Exit criteria:
- documents have no incomplete sections
- core boundaries are agreed
- planner strategy, sufficiency strategy, repetition guard, run ledger, and capability policy have initial decisions
- no major contradiction between docs
- implementation sequence is clear
- open questions are either resolved or explicitly deferred

Validation:
- incomplete-marker scan
- self-review for contradictions
- user review

Promotion decision:
- move to implementation planning only after user approval.

## Milestone 1: v4 Service Shell

Goal:
- Wrap v3 indexing, retrieval, ranking, and context assembly behind v4-style typed service contracts without changing v3 behavior.

Capabilities:
- central `CapabilityPolicy`
- append-only run ledger
- load/validate index
- retrieve evidence
- rank evidence
- build context pack
- direct read service
- emit service result envelopes
- emit telemetry artifacts

Explicitly excluded:
- multi-pass agent loop
- write tools
- command execution
- patching
- product UI

Primary files likely involved:
- v4 service package
- adapter layer to v3 retrieval/ranking/context
- contract schemas
- service telemetry writer
- contract tests

Exit criteria:
- one read-only answer path can call v3-derived services through v4 contracts
- every service returns structured result envelopes
- degraded states are visible
- service telemetry can be inspected after a run
- v3 baseline remains runnable

Validation tasks:
- contract tests for each service
- fixture repo retrieval smoke test
- vector/BM25 availability test
- reranker unavailable fallback test
- context pack token budget test

Success metrics:
- service output matches or intentionally explains deviation from v3
- no significant latency regression beyond wrapper overhead
- no silent fallback

Kill/pivot criteria:
- adapter requires invasive v3 runtime changes
- service boundary cannot expose required provenance
- telemetry cannot identify degraded modes

## Milestone 2: Read-Only Agent Loop

Goal:
- Implement bounded multi-pass read-only reasoning using typed state, evidence memory, sufficiency checks, and grounded response composition.

Capabilities:
- task intake
- deterministic routing
- bounded planning
- evidence acquisition
- direct read/search as precision tools
- sufficiency decision
- claim support map
- stop reasons
- run ledger

Explicitly excluded:
- command execution
- patching
- write permissions
- repair loops

Exit criteria:
- simple questions use direct or single-pass mode without unnecessary loops
- hard questions can perform bounded additional evidence passes
- unsupported claims are removed, softened, or marked uncertain
- every final answer has a stop reason
- evidence support map exists for important claims

Validation tasks:
- read-only benchmark subset
- hard repo-question subset
- low-evidence query tests
- repeated-state guard tests
- budget exhaustion tests
- claim support consistency tests

Success metrics:
- equal or better answer quality than v3 on targeted read-only tasks
- lower or comparable token usage on simple tasks
- fewer hallucinated unsupported claims
- visible blocked states when evidence is insufficient

Kill/pivot criteria:
- multi-pass increases token usage without improving hard tasks
- sufficiency decisions are too noisy to guide the loop
- final answers become less grounded than v3

## Milestone 3: Verification-Only Execution

Goal:
- Add allowlisted command execution and verification gates without allowing source edits.

Capabilities:
- command policy model
- command sandbox abstraction
- allowlisted read-only/test commands
- fixed cwd and timeout
- output artifacts
- verification plan
- verification gate results
- blocked/failed/skipped gate semantics

Explicitly excluded:
- patch application
- dependency installation by default
- network command execution by default
- rollback

Exit criteria:
- verification commands run through structured command requests
- failed tests block success claims
- skipped gates are visible
- denied commands return structured policy/sandbox errors
- command output is stored as artifacts

Validation tasks:
- command allowlist tests
- command deny tests
- timeout tests
- missing command tests
- failed test command tests
- verification summary tests

Success metrics:
- no false success after failed required verification
- command traces are reproducible
- unsafe commands denied by policy
- verification-only mode works on existing repositories

Kill/pivot criteria:
- command execution cannot be made safe enough for normal use
- verification adds high latency without useful signal
- policy decisions are too hard to explain to users

## Milestone 4: Patch-Capable Workflow

Goal:
- Add safe patch application with stale-context checks, diff inspection, verification, and bounded repair.

Capabilities:
- patch plans
- path validation
- artifact sandbox
- patch drafts
- patch validation
- patch application
- patch manifests
- diff inspection
- post-patch verification
- bounded repair

Explicitly excluded initially:
- broad refactors
- dependency installation
- destructive operations
- full autonomous dangerous mode
- broad rollback until patch manifests are proven reliable

Exit criteria:
- small code changes can complete end to end
- stale target context blocks patching
- diff inspection catches unrelated/risky changes
- focused verification runs after patch
- failed verification triggers repair or truthful blocked state
- final response distinguishes changed, verified, skipped, and blocked

Validation tasks:
- single-file bug fix benchmark
- multi-file small behavior change
- stale-context simulation
- dirty workspace simulation
- patch conflict simulation
- failed verification repair
- failed verification stop
- unrelated diff detection

Success metrics:
- high verified completion rate on small patch tasks
- low unrelated diff rate
- low false success rate
- bounded repair does not wander
- token usage remains lower than generic exploratory agent pattern on targeted tasks

Kill/pivot criteria:
- patch application frequently touches wrong files
- verification failures are hidden or misclassified
- repair loops expand scope uncontrollably
- dirty workspace behavior risks user changes

## Milestone 5: Extended Task Coverage

Goal:
- Expand from small patch tasks to broader practical coding workflows only after Milestone 4 is reliable.

Candidate capabilities:
- test generation
- refactor support
- broader verification plans
- dependency-aware tasks with approval
- project-specific command profiles
- richer call graph use
- task session resume

Exit criteria:
- each new task class has benchmarks
- each new tool has contract tests
- each new permission increase has UX and telemetry
- no regression in small task safety

Validation tasks:
- task-class-specific benchmark sets
- regression suite from Milestones 1-4
- manual adversarial safety cases

Success metrics:
- measurable improvement in at least one new task class
- no safety regression
- setup remains understandable

Kill/pivot criteria:
- product complexity grows faster than reliability
- new capabilities mostly duplicate generic agents without HOM-LLM advantage
- benchmark signal is too weak to justify expansion

## Milestone 6: Product Track Decision

Goal:
- Decide whether v4 is ready to become a product-facing system.

Product-track criteria:
- clear install/setup path
- reliable indexing experience
- explainable modes and approvals
- safe workspace write behavior
- useful trace artifacts
- repeatable verification
- acceptable latency
- acceptable token/cost profile
- documented limitations
- benchmark evidence of advantage in defined task classes

Required evidence:
- read-only benchmark comparison
- patch-task benchmark comparison
- token/cost comparison
- latency comparison
- safety simulation results
- judge/human review sample
- failure taxonomy
- user-facing mode design

Decision outcomes:
- `continue_research`: architecture promising, product not ready
- `product_candidate`: begin UX/install/product hardening
- `narrow_product`: ship a constrained use case only
- `pause_or_pivot`: evidence does not justify further investment

## Evaluation Strategy

v4 evaluation should have multiple layers.

### Contract Evaluation

Checks:
- service schemas
- tool schemas
- permission decisions
- sandbox decisions
- telemetry presence
- artifact references
- error codes

Purpose:
- prove implementation respects architecture.

### Retrieval Evaluation

Checks:
- relevant evidence recall
- ranking quality
- context efficiency
- vector vs sparse contribution
- reranker latency
- degraded fallback behavior

Purpose:
- protect HOM-LLM's core advantage.

### Answer Evaluation

Checks:
- semantic correctness
- factual consistency
- completeness
- clarity
- relevance
- hallucination safety
- verbosity
- evidence citation quality

Purpose:
- compare read-only behavior against v3 and baselines.

### Agent Loop Evaluation

Checks:
- number of passes
- token usage per pass
- evidence gain per pass
- repeated-state stops
- budget exhaustion behavior
- blocked-state correctness

Purpose:
- prove multi-pass is bounded and useful.

### Write/Execute Evaluation

Checks:
- patch correctness
- verification pass rate
- false success rate
- command safety
- sandbox denial correctness
- dirty workspace safety
- stale-context blocking
- repair effectiveness

Purpose:
- prove agentic write behavior is safe enough to trust.

### Product Evaluation

Checks:
- setup time
- mode clarity
- user trust
- trace inspectability
- cost predictability
- failure explainability

Purpose:
- decide whether this can become a usable product.

## Benchmark Sets

Recommended benchmark layers:

### Internal Canary

Small, fast, repeatable.

Use for:
- every change
- quick regression checks
- service contract sanity

### Read-Only Repository QA

Questions about existing repositories.

Use for:
- retrieval/ranking/context validation
- answer quality comparison
- token efficiency comparison

### Grounding Stress Set

Queries designed to expose hallucination.

Use for:
- claim support map validation
- repo gap behavior
- unsupported claim suppression

### Patch Microbench

Small controlled patch tasks.

Use for:
- path validation
- patch planning
- verification gates
- repair behavior

### Safety Simulation Set

Artificial cases for:
- stale context
- dirty workspace
- denied paths
- command denial
- sandbox escape attempts
- dependency install requests
- failed verification

### External Benchmarks

Potential later targets:
- SWE-bench style tasks
- Terminal-Bench style tasks
- custom repository task suites

Use later, not first.

Reason:
- external benchmarks are useful for positioning, but early v4 needs controlled internal tests to validate architecture and safety.

## Baseline Strategy

Baselines should answer different questions.

### v3 Baseline

Question:
- Did v4 preserve or improve HOM-LLM's existing read-only strengths?

### Sparse-Only / Vector Variants

Question:
- Which retrieval policy improves quality vs latency vs token use?

### Generic Agent Baseline

Question:
- Does the RAG-first approach reduce wandering and token waste?

### Cursor/Codex-Style Manual Baseline

Question:
- Where does v4 stand against practical coding assistants?

### Ablations

Examples:
- no reranker
- sparse-only
- vector-lite
- no graph expansion
- no sufficiency gate
- no claim support map
- single-pass only

Question:
- Which components actually create the advantage?

## Judge Strategy

LLM judges are useful but unstable.

Rules:
- judge output can support decisions but should not be the only evidence
- partial judge runs must be marked incomplete
- provider failures must be visible
- use stable JSONL artifacts
- compare nested metrics, not just final labels
- include human review samples for major decisions

Judge providers:
- use whichever provider is reliable and affordable
- rate limit aggressively
- batch in small chunks
- resume partial runs

Judge result states:
- `complete`
- `partial`
- `failed`
- `inconclusive`

Never treat a partial judge run as a full benchmark result.

## Cost and Token Accounting

Token efficiency is part of the thesis, so it must be measured from the start.

Track:
- retrieval/query tokens if any
- reranker cost/latency
- LLM input tokens
- LLM output tokens
- tool call count
- file read count
- command count
- context pack size
- final answer size
- total run wall-clock time

Report:
- quality per 1k tokens
- verified completion per dollar
- answer correctness vs context size
- latency by stage
- retrieval/ranking/generation split

## Latency Accounting

Latency matters for product viability.

Track:
- indexing time
- retrieval time
- ranking time
- context time
- planning LLM time
- generation LLM time
- command execution time
- verification time
- artifact write time

Important lesson from current experiments:
- ranking latency and device usage must be visible
- vector retrieval returning zero candidates must be visible
- judge partial completion must be visible

## Regression Policy

Every milestone should maintain regression sets.

Regression classes:
- answer quality
- retrieval channel behavior
- ranking latency
- context token budget
- telemetry completeness
- sandbox policy
- command denial
- patch safety
- verification blocking

No change should be promoted if it improves one metric while silently breaking safety or telemetry.

## Initial Architecture Decisions Before Implementation

The first implementation plan should proceed with these initial decisions unless user review changes them.

- package location: `src/homllm_v4/` to avoid contaminating v3
- schemas: dataclasses for internal contracts, Pydantic only at CLI/API/config boundaries if needed
- run ledger: append-only `events.jsonl` as source of truth, with derived snapshots for debugging
- artifacts: `.homllm/runs/<run_id>/` with `metadata.json`, `task.json`, `events.jsonl`, `snapshots/`, `evidence/`, `context/`, `commands/`, `patches/`, `verification/`, and `response/`
- execution backend: local restricted process first for `VerifyOnly`, worktree/container later
- command allowlist: test/lint/inspect commands only
- benchmark suite: internal canary plus read-only QA plus safety simulation fixtures
- planner strategy: hybrid planner with deterministic runtime policy and optional LLM strategic planner
- sufficiency strategy: deterministic-first scoring with LLM assistance only for ambiguous or high-risk cases
- repetition guard: compare evidence content overlap, not only action parameters
- runtime policy: central `CapabilityPolicy` object owns permissions, allowed tools, verification requirements, budgets, sandbox policy, and escalation rules

These are starting recommendations, not irreversible decisions.

## Architecture Tiers For Implementation

Milestone plans should preserve three tiers:

### Tier A: Core Runtime Law

Mandatory:
- `TaskState`
- `EvidenceWorkspace`
- `CapabilityPolicy`
- `CapabilityResult`
- `VerificationGate`
- budget enforcement
- stop reasons
- run ledger events

Tier A code should stay small, deterministic, and heavily tested.

### Tier B: Core Services

Required for normal execution:
- index validation
- retrieval
- ranking
- context packing
- direct read
- planner
- verification

Tier B services may degrade, but degraded status must be explicit.

### Tier C: Advisory Intelligence

Optional/degradable:
- advanced hallucination signals
- style/readability checks
- experimental claim quality heuristics
- optional answer polish

Tier C must not become a hidden completion gate in early milestones.

## First Implementation Plan Boundary

The first implementation plan should cover only Milestone 1.

It should not include:
- patching
- command execution
- sandbox runtime
- approval UX
- repair loops
- product UI

Milestone 1 is successful if:
- v4 can call v3-derived RAG services through clean contracts
- v4 records service telemetry
- v4 can produce a read-only context pack
- v3 remains untouched
- tests prove the boundary works

This is intentionally modest. It creates the foundation for everything else.

## Risk Register

### Risk: v4 Becomes Another Large Runtime

Mitigation:
- enforce module boundaries
- contract tests
- small milestones
- no CLI-first orchestration

### Risk: RAG Advantage Gets Diluted

Mitigation:
- preserve retrieval/ranking diagnostics
- evaluate ablations
- measure token efficiency
- keep RAG first in read/write tasks

### Risk: Write Capability Arrives Before Safety

Mitigation:
- no patch milestone before sandbox/verification design
- command execution before patching
- verification gates must block completion

### Risk: Benchmarks Become Too Expensive

Mitigation:
- small canaries
- batch judge runs
- partial result support
- local deterministic tests for contracts

### Risk: Judge Results Mislead Direction

Mitigation:
- compare telemetry and artifacts
- include human review
- inspect regressions manually
- never promote from partial judge results alone

### Risk: Product Hope Distorts Engineering Discipline

Mitigation:
- product track requires evidence
- research milestones remain narrow
- kill/pivot criteria are explicit
- do not build UX before core behavior is proven

## Current Recommendation

The next step after architecture approval should be a written implementation plan for Milestone 1: v4 Service Shell.

That plan should:
- use TDD
- define exact files to create
- wrap v3 services without rewriting them
- add contract tests before implementation
- produce one minimal read-only path through v4 service contracts
- preserve v3 behavior
- avoid write/execute functionality entirely

## Final Conclusion

v4 should move forward, but only through measured gates.

The correct path is:

```text
Architecture lock
  -> v4 service shell
  -> read-only agent loop
  -> verification-only execution
  -> patch-capable workflow
  -> broader task coverage
  -> product-track decision
```

This path protects the original product ambition without pretending the system is product-ready today. It gives HOM-LLM a realistic chance to become a strong coding agent by preserving its RAG advantage, adding agency carefully, and forcing every major claim to be validated.
