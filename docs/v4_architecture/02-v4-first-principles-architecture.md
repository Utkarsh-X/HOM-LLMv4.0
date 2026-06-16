# HOM-LLM v4 First-Principles Architecture

Date: 2026-05-09

## Purpose

This document defines HOM-LLM v4 from first principles. It is not an implementation plan and it is not a refactor plan. It describes the system we should build only after the architecture is reviewed and accepted.

The core goal is to design a production-capable, evidence-first coding agent that uses advanced code RAG as its primary advantage while supporting bounded multi-pass planning, tool use, writing, execution, and verification.

## Design Thesis

Generic coding agents often waste tokens because they discover evidence through repeated raw file reads, shell commands, and trial-and-error loops. HOM-LLM v4 should invert that pattern.

The default path should be:

1. Build or load a repository evidence substrate.
2. Retrieve and rank grounded evidence before expensive reasoning.
3. Use the LLM to decide only when deterministic services are insufficient.
4. Invoke tools through typed, permissioned contracts.
5. Verify claims, patches, and completion states before reporting success.

The system should not be "an agent with RAG added." It should be "a RAG-first evidence system with bounded agency."

## Non-Negotiable Principles

### 1. Evidence Before Action

The system must gather enough relevant evidence before writing, executing, or making strong claims. For patch tasks, evidence includes target files, current behavior, expected behavior, and verification options.

Question to ask:
- What evidence justifies this action?
- Is the evidence fresh enough?
- Which files, symbols, tests, or commands support the decision?

### 2. RAG Is The Primary Evidence Layer

Raw file reads and shell commands are allowed, but they should not be the first source of truth for ordinary repository understanding. RAG services should provide candidate evidence, context packs, provenance, and retrieval diagnostics.

Question to ask:
- Can retrieval answer this cheaper and more systematically than exploratory tool use?
- If retrieval failed, do we know why?

### 3. Tools Are Typed, Permissioned, And Auditable

Every tool must have a schema, permission level, side-effect classification, telemetry output, and failure policy. Tools should not return arbitrary unstructured text as the only result.

Question to ask:
- What can this tool change?
- What are its failure modes?
- What telemetry proves what happened?

### 4. Writing Is A Verified Lifecycle

Writing files is not a single operation. It is a lifecycle:

1. Identify target files.
2. Build a patch plan.
3. Check stale context.
4. Apply patch.
5. Record diff manifest.
6. Run verification.
7. Repair, rollback, or stop with a blocked state.
8. Explain the final state.

Question to ask:
- What proves this patch is correct?
- What happens if verification fails?
- Can the system recover without hiding risk?

### 5. Multi-Pass Is Bounded

v4 must support multiple passes, but not unbounded wandering. Budgets must apply to LLM calls, retrieval passes, file reads, tool calls, patch attempts, verification attempts, tokens, and time.

Question to ask:
- What new information will the next pass acquire?
- Has the state changed enough to justify continuing?
- Is the system repeating itself?

### 6. Verification Is A Gate, Not A Decoration

Verification must be capable of blocking success claims. The system should never say a patch is complete if tests failed, verification could not run, or required evidence is missing.

Question to ask:
- Which gates are required for this task?
- Which gates passed, failed, or were skipped?
- Is a skipped gate acceptable or blocking?

### 7. Evaluation Drives Promotion

No subsystem should be promoted because it feels architecturally elegant. It must improve measurable behavior or reduce risk.

Question to ask:
- Which benchmark or regression set proves this works?
- What task class benefits?
- What task class gets worse?

## Target System Model

```text
User Task
  -> Task Intake
  -> Task Router
  -> Planner
  -> Evidence Workspace
  -> Tool Executor
  -> Patch/Write Lifecycle
  -> Verification Gates
  -> Response Composer
  -> Telemetry and Evaluation Ledger
```

The architecture is deliberately layered. Lower layers provide typed capabilities. Higher layers decide when and why to invoke them.

## Core Runtime Objects

### Task

The immutable user request plus normalized metadata.

Required fields:
- `task_id`
- `user_query`
- `workspace_root`
- `task_class`
- `requested_mode`
- `permission_profile`
- `created_at`

Task classes:
- `answer`
- `search`
- `explain`
- `debug`
- `implement`
- `refactor`
- `test`
- `review`
- `unknown`

### Task State

The mutable orchestration state for one run.

Required fields:
- `phase`
- `iteration`
- `budget_state`
- `plan_state`
- `evidence_state`
- `tool_state`
- `patch_state`
- `verification_state`
- `stop_reason`

State must be serializable so runs can be inspected, resumed, or evaluated.

### Evidence Workspace

The structured memory of what the system knows about the repository for the task.

Required fields:
- `retrieval_attempts`
- `ranked_evidence_sets`
- `context_packs`
- `direct_file_reads`
- `symbol_refs`
- `claim_support_map`
- `known_gaps`
- `staleness_markers`

This is not free-form chat memory. It is a typed evidence ledger.

### Plan

A bounded, revisable task plan.

Required fields:
- `goal`
- `steps`
- `active_step`
- `required_tools`
- `required_verification`
- `risk_flags`
- `revision_count`

Plans should be updated when evidence changes, but plan changes must be explicit and logged.

### Tool Call

A typed invocation of a capability.

Required fields:
- `tool_name`
- `input`
- `permission_required`
- `side_effect_level`
- `start_time`
- `end_time`
- `ok`
- `output`
- `error`
- `artifacts`

### Verification Gate

A required or advisory check.

Required fields:
- `gate_name`
- `gate_type`
- `blocking`
- `status`
- `evidence`
- `failure_summary`
- `repair_suggestion`

Gate types:
- `grounding`
- `syntax`
- `unit_test`
- `integration_test`
- `lint`
- `typecheck`
- `diff_safety`
- `stale_context`
- `user_approval`

## Primary Layers

### 1. Task Intake Layer

Responsibilities:
- Normalize the user request.
- Identify workspace and repo state.
- Determine whether indexing is available or stale.
- Resolve permission profile.
- Create the initial task state.

Inputs:
- raw user query
- workspace root
- user-selected mode or defaults
- environment information

Outputs:
- `Task`
- initial `TaskState`

Must not:
- retrieve evidence
- call the LLM
- mutate files

Failure modes:
- workspace missing
- repo state unreadable
- index missing
- permission profile invalid

### 2. Task Router

Responsibilities:
- Decide the initial execution path.
- Route simple tasks to direct evidence answer.
- Route complex tasks to planner.
- Route patch tasks to write-capable lifecycle only when permission allows.

Modes:
- `single_pass_answer`
- `read_only_multipass`
- `verification_only`
- `patch_capable`
- `blocked_requires_permission`

Must consider:
- task class
- user request
- index state
- available tools
- permission profile
- verification requirements

Routing should be deterministic where possible. LLM-based routing may be used only after deterministic classification is insufficient.

### 3. Planner

Responsibilities:
- Convert task into a bounded plan.
- Decide what evidence is needed.
- Decide which tools are allowed and necessary.
- Revise the plan when verification fails or evidence contradicts assumptions.

Planner input:
- `Task`
- `TaskState`
- evidence summary
- tool availability
- budget state

Planner output:
- typed `Plan`
- next action
- rationale
- required verification gates

Planner constraints:
- no direct file mutation
- no direct command execution
- no hidden state changes
- no unbounded retries

Planner failure modes:
- invalid structured output
- unsafe tool request
- insufficient evidence
- budget exhausted

### 4. Evidence Services

Evidence services are deterministic or mostly deterministic subsystems that acquire repository evidence.

Services:
- `IndexService`
- `EvidenceRetrievalService`
- `EvidenceRankingService`
- `ContextPackService`
- `DirectReadService`
- `RepoSearchService`
- `SymbolGraphService`

Core rule:
- `DirectReadService` and `RepoSearchService` are precision tools, not replacements for RAG.

Evidence services should produce:
- provenance
- confidence
- source channel
- staleness status
- token estimates
- diagnostics

### 5. Tool Executor

Responsibilities:
- Enforce permission checks.
- Execute typed tools.
- Capture outputs and artifacts.
- Apply retry policy where safe.
- Refuse unsafe or unsupported calls.

Tool categories:
- read-only tools
- repository inspection tools
- execution tools
- write tools
- patch tools
- verification tools

Side-effect levels:
- `none`
- `read_workspace`
- `execute_readonly`
- `write_workspace`
- `external_network`
- `dangerous`

v4 should initially support:
- `retrieve_evidence`
- `rank_evidence`
- `build_context_pack`
- `search_repo`
- `read_file`
- `list_files`
- `run_command` with allowlist
- `apply_patch`
- `run_tests`
- `inspect_diff`

### 6. Patch / Write Lifecycle

Responsibilities:
- Convert a patch plan into safe file changes.
- Preserve user changes.
- Avoid stale context edits.
- Produce a diff manifest.
- Trigger verification gates.

Required preconditions:
- target files identified
- current file content loaded
- patch intent known
- permission allows write
- verification strategy selected

Patch state:
- `planned`
- `applied`
- `verification_pending`
- `verified`
- `failed_verification`
- `repairing`
- `blocked`
- `rolled_back`

Important rule:
- v4 should prefer patch application over full-file rewrite unless the file is newly created or explicitly replaced.

### 7. Verification Layer

Responsibilities:
- Select required gates.
- Run verification tools.
- Interpret outputs.
- Block success if required gates fail.
- Suggest repair when failure is actionable.

Verification should happen at multiple levels:
- pre-action verification
- post-retrieval sufficiency
- post-generation grounding
- post-patch tests
- final completion gate

Verification outputs must be structured. A failing test is not just text; it is a gate failure with command, exit code, relevant output, and next-step implications.

### 8. Response Composer

Responsibilities:
- Produce the final user-facing answer.
- Explain what was done.
- Cite evidence and verification results.
- Surface uncertainty, skipped gates, and blocked states.

Response types:
- direct answer
- evidence summary
- plan proposal
- patch summary
- verification failure report
- blocked permission request

The response composer should not invent facts. It should consume the evidence workspace and verification state.

### 9. Telemetry And Evaluation Ledger

Responsibilities:
- Persist task state transitions.
- Persist tool calls.
- Persist evidence attempts.
- Persist token usage.
- Persist patch diffs.
- Persist verification gates.
- Support run comparison and benchmark evaluation.

This ledger should be designed from day one, not added later.

## Agent Loop

The v4 loop should be explicit:

```text
1. Intake task
2. Route mode
3. Build or load plan
4. Acquire evidence
5. Check sufficiency
6. Choose next action
7. Execute allowed action
8. Update state
9. Verify if required
10. Stop, answer, revise, or block
```

The loop can continue only when:
- there is a specific next action
- the action is allowed
- the budget permits it
- the state is not repeating
- expected information gain is non-zero

Stop reasons:
- `answered`
- `verified_complete`
- `blocked_permission`
- `blocked_missing_evidence`
- `blocked_verification_failed`
- `budget_exhausted`
- `repeated_state`
- `unsafe_action_refused`
- `user_input_required`

## Permission Model

Permission profiles:

### ReadOnly

Allowed:
- retrieve evidence
- rank evidence
- build context
- search repo
- read files
- inspect git status

Not allowed:
- write files
- run arbitrary commands
- network calls except configured model providers

### VerifyOnly

Allowed:
- all ReadOnly actions
- allowlisted commands such as tests, lint, typecheck, build

Not allowed:
- file mutation
- destructive commands

### WorkspaceWrite

Allowed:
- all VerifyOnly actions
- patch files
- create new files
- update generated artifacts only when explicitly part of task

Required:
- diff manifest
- post-change verification

### Elevated

Allowed only with explicit user approval:
- commands with broader side effects
- dependency installation
- migration scripts
- workspace cleanup

Dangerous operations should remain opt-in and should never be silently chosen by the planner.

## Memory Model

v4 should avoid vague "agent memory." It needs typed memory scopes.

### Run Memory

Short-lived state for a single task:
- plan
- evidence
- tool calls
- patches
- verification

### Repository Memory

Derived artifacts:
- index
- graph
- embeddings
- file metadata
- historical benchmark results

### User / Product Memory

Future product feature, not required for initial v4:
- user preferences
- project conventions
- repeated workflow preferences

Rule:
- Run memory can affect current decisions.
- Repository memory can inform evidence.
- User/product memory must never override evidence or verification.

## Error Handling Philosophy

Errors should become structured state, not hidden retries.

Examples:
- Reranker unavailable -> ranking output includes degraded mode.
- Vector search fails -> retrieval output includes vector failure and fallback path.
- Test command fails -> verification gate blocks completion.
- Patch does not apply -> patch state becomes blocked or repairable.
- Judge output partial -> evaluation result is incomplete, not successful.

The system should prefer a truthful blocked state over a false success.

## v4 Module Boundary Proposal

This is a conceptual package map, not an implementation command.

```text
homllm_v4/
  app/
    task_app.py
    session.py
  core/
    task.py
    state.py
    budgets.py
    permissions.py
    events.py
  planning/
    planner.py
    router.py
    policies.py
  evidence/
    retrieval_service.py
    ranking_service.py
    context_service.py
    evidence_types.py
  tools/
    registry.py
    executor.py
    read_tools.py
    search_tools.py
    command_tools.py
    patch_tools.py
  verification/
    gates.py
    test_runner.py
    grounding.py
    diff_safety.py
  patching/
    planner.py
    applier.py
    manifest.py
  generation/
    llm_service.py
    prompt_compiler.py
    output_parsers.py
  telemetry/
    ledger.py
    schemas.py
  eval/
    benchmark.py
    run_compare.py
```

Open question:
- This package map should probably live beside v3 first, not replace `src/homllm/`.
- Final location should be decided after service contracts are written.

## Product-Oriented Constraints

v4 should be designed so it can become a product if the thesis works.

Product requirements:
- clear install path
- local repository indexing
- predictable permission prompts
- visible run trace
- explainable cost/token use
- safe patch workflow
- repeatable verification
- resumable or inspectable task sessions
- minimal config surface for normal users
- advanced config surface for researchers

Research flexibility must not destroy product boundaries. The clean compromise is:
- stable service contracts
- experimental policy presets
- benchmark-first promotion

## Design Risks

### Risk 1: Rebuilding Too Much

v4 should not rewrite the RAG engine from scratch unless a subsystem blocks the architecture. The current retrieval/ranking/context stack is valuable.

Mitigation:
- wrap existing services first
- replace internals only after contract tests exist

### Risk 2: Repeating v3 Runtime Coupling

If v4 starts with one large runtime file, it will recreate the same ceiling.

Mitigation:
- application service owns orchestration
- CLI/API are thin adapters

### Risk 3: Tool Explosion

Adding too many tools early will increase complexity and reduce reliability.

Mitigation:
- start with minimal tools
- every tool must justify itself through benchmark tasks

### Risk 4: Verification Theater

Verification that cannot block completion is not verification.

Mitigation:
- verification gates are typed
- required gates must block success
- skipped gates must be visible

### Risk 5: Agentic Token Waste

Multi-pass can become expensive and worse than single-pass.

Mitigation:
- route simple tasks to direct mode
- cap budgets
- compare token/tool cost in every eval run

## Initial v4 Milestones

### Milestone 0: Architecture Lock

Artifacts:
- asset map
- first-principles architecture
- tool/service contracts
- loop and memory design
- write/execute/verify design
- migration and validation plan

Exit criteria:
- architecture reviewed
- no major unresolved boundary questions
- no implementation started

### Milestone 1: Service Shell

Goal:
- Wrap v3 RAG services behind v4-style typed interfaces without changing behavior.

Exit criteria:
- one read-only answer path works through service boundaries
- telemetry ledger records state transitions
- v3 baseline remains untouched

### Milestone 2: Read-Only Multi-Pass

Goal:
- Support bounded evidence acquisition loops using typed evidence state.

Exit criteria:
- improves targeted hard read-only tasks
- does not regress simple tasks
- stops correctly when evidence is insufficient

### Milestone 3: Verification-Only Tools

Goal:
- Add allowlisted command execution for tests/lint/build without file mutation.

Exit criteria:
- verification can block incorrect success
- command traces are structured
- repeated failures stop safely

### Milestone 4: Patch-Capable Workflow

Goal:
- Add safe patch application and post-patch verification.

Exit criteria:
- small patch tasks can complete end to end
- failures produce repair or blocked states
- diff manifest and verification evidence are always present

### Milestone 5: Product Track Decision

Goal:
- Decide whether v4 is ready to become a product-facing system.

Exit criteria:
- internal benchmark evidence supports a real advantage
- cost/latency are acceptable
- setup and UX path are clear

## Current Architectural Decision

v4 should be designed beside v3. v3 should remain stable and usable while v4 architecture and service contracts are developed. The first implementation, when approved, should be a thin service shell around v3 capabilities rather than a full rewrite.

The next document should define tool and service contracts in detail.

