# HOM-LLM v4 Agent Loop and Memory Design

Date: 2026-05-09

## Purpose

This document defines the bounded multi-pass agent loop and memory model for HOM-LLM v4.

v4 should support agentic behavior, but it must not become an uncontrolled tool-calling loop. The agent loop must be explicit, inspectable, budgeted, evidence-first, and verification-aware.

The goal is not to make the system "more agentic" in the generic sense. The goal is to let the system take additional steps only when those steps are justified by evidence gaps, verification needs, or safe repair opportunities.

## Design Position

v4 should treat the LLM as a decision component inside a controlled runtime, not as the runtime itself.

The runtime owns:
- state transitions
- budgets
- permission enforcement
- tool execution
- evidence freshness
- verification gates
- stop conditions
- telemetry

The LLM may help with:
- interpreting the task
- proposing a plan
- selecting evidence needs
- drafting patches
- explaining failures
- revising after new evidence

The LLM must not own:
- unrestricted tool access
- hidden retries
- silent mutation
- success/failure classification without verification
- unstructured memory that becomes the source of truth

## Core Loop Principle

Every pass through the loop must answer four questions:

1. What is currently known?
2. What is still missing or uncertain?
3. What is the cheapest safe next action that can reduce that uncertainty or complete the task?
4. What condition will stop the loop?

If the system cannot answer these questions, it should stop with a structured blocked state instead of wandering.

## Runtime State Machine

The v4 agent loop should be represented as a state machine.

```text
created
  -> intake_complete
  -> routed
  -> planning
  -> acquiring_evidence
  -> checking_sufficiency
  -> deciding_action
  -> executing_action
  -> updating_memory
  -> verifying
  -> composing_response
  -> stopped
```

Some phases are skipped depending on task class and permission profile.

Examples:
- A simple read-only answer may skip patching and command execution.
- A verification-only task may skip patch application.
- A patch task cannot skip stale-context checks, diff inspection, and required verification.

## Agent Loop Phases

### 1. `created`

The run exists, but no normalized task state has been created.

Inputs:
- user request
- workspace root
- environment metadata
- user-selected mode if provided

Outputs:
- raw run record

Allowed side effects:
- create run artifact directory

Must not:
- call LLM
- retrieve evidence
- execute commands
- mutate workspace

### 2. `intake_complete`

The user request has been normalized into a `Task`.

Responsibilities:
- classify the task
- capture workspace identity
- capture permission profile
- inspect high-level repo state
- identify whether an index exists
- initialize budgets

Outputs:
- `Task`
- initial `TaskState`
- initial `BudgetState`

Failure states:
- `workspace_unavailable`
- `permission_profile_invalid`
- `repo_state_unreadable`

### 3. `routed`

The system chooses the initial execution mode.

Routing modes:
- `direct_answer`
- `read_only_multipass`
- `verification_only`
- `patch_capable`
- `blocked_requires_permission`

Routing should be deterministic first. LLM routing is allowed only when deterministic classification is inconclusive.

Routing inputs:
- task class
- requested mode
- permission profile
- index state
- write requirement
- verification requirement
- risk flags

Routing outputs:
- selected mode
- required loop capabilities
- disallowed capabilities
- initial stop rules

### 4. `planning`

The planner produces or revises a bounded plan.

Planner output must be structured:

```python
@dataclass(frozen=True)
class AgentPlan:
    plan_id: str
    task_id: str
    goal: str
    steps: tuple[PlanStep, ...]
    active_step_id: str | None
    required_evidence: tuple[EvidenceNeed, ...]
    required_tools: tuple[str, ...]
    required_verification: tuple[str, ...]
    risk_flags: tuple[str, ...]
    revision: int
```

Planner rules:
- Plans are allowed to change, but every revision must state why.
- A revised plan must reference new evidence, new failure information, or changed user constraints.
- A plan must not request tools outside the current permission profile.
- A plan must not mark a task complete; completion belongs to verification and response composition.

### Concrete Planner Strategy

v4 should use a hybrid planner, not an LLM-only planner.

The split:
- deterministic router decides initial mode where possible
- deterministic runtime policy owns allowed tools, budgets, retries, permissions, sandbox limits, and required verification
- LLM-backed strategic planner is used for decomposition, ambiguous task interpretation, evidence hypotheses, patch intent, and repair reasoning
- deterministic validator checks every planner output before dispatch

The planner should not run on every loop iteration by default. It should run when:
- no valid plan exists
- evidence changes the task understanding
- a blocking verification failure needs repair reasoning
- the runtime cannot choose between materially different safe next actions
- user instruction changes scope

The planner should not run when:
- the next action is a deterministic continuation of the current step
- only budget accounting changed
- a tool result can be handled by fixed policy
- the system is trying to avoid a failed gate without new evidence

This prevents the planner from becoming "the LLM secretly controlling everything" while still allowing flexible reasoning where rules are insufficient.

Bad plan example:
- "Inspect files, make changes, run tests."

Good plan example:
- "Retrieve evidence for auth middleware flow, read the two highest-ranked source files, identify the validation branch, patch the missing expiry check, run the auth unit tests, inspect diff, then compose a verified summary."

### 5. `acquiring_evidence`

The system gathers evidence through retrieval, ranking, context packing, direct reads, or repo search.

Evidence acquisition should start with RAG services for repository understanding, then use direct reads/search for precision.

Allowed actions:
- load/validate index
- retrieve evidence
- rank evidence
- build context pack
- read specific files
- search repo for precise symbols or strings

Evidence acquisition must produce:
- evidence items
- provenance
- confidence
- token estimate
- freshness markers
- retrieval diagnostics
- known gaps

Evidence acquisition must not:
- mutate workspace files
- execute arbitrary commands
- assume retrieved snippets are fresh when target files have changed

### 6. `checking_sufficiency`

The system decides whether current evidence is enough for the next decision.

Sufficiency is task-specific.

For read-only answers, evidence is sufficient when:
- key claims have supporting sources
- retrieved evidence covers the main entities in the user request
- unresolved gaps are either minor or explicitly reportable

For patch tasks, evidence is sufficient when:
- target files are identified
- current file contents are fresh
- expected behavior is understood
- verification strategy is available
- patch risk is bounded

For debugging tasks, evidence is sufficient when:
- observed failure is captured
- likely failing component is identified
- next diagnostic command or patch is justified

Sufficiency output:

```python
@dataclass(frozen=True)
class SufficiencyDecision:
    sufficient: bool
    confidence: float
    missing: tuple[EvidenceNeed, ...]
    supported_claims: tuple[str, ...]
    unsupported_claims: tuple[str, ...]
    next_recommended_action: str
    rationale: str
```

Rule:
- Low sufficiency should not automatically trigger more retrieval. It should trigger a specific next evidence action or a blocked state.

### 7. `deciding_action`

The system chooses the next action.

Action types:
- `retrieve_more_evidence`
- `read_precise_file`
- `search_precise_symbol`
- `revise_plan`
- `run_verification_command`
- `draft_patch`
- `apply_patch`
- `inspect_diff`
- `repair_after_failure`
- `compose_answer`
- `ask_user`
- `stop_blocked`

The next action must include:
- reason
- expected information gain or task progress
- required permission
- expected side effect
- budget impact
- stop condition if action fails

The runtime must reject actions when:
- permission is insufficient
- budget is exhausted
- action repeats a prior action without changed inputs
- action has side effects not allowed by current mode
- stale context makes the action unsafe
- verification requirements are unknown for a write task

### 8. `executing_action`

The tool executor runs the selected action through the tool registry.

Rules:
- The planner never calls arbitrary functions directly.
- Every action becomes a typed tool or service call.
- The executor enforces permission and side-effect policy.
- Outputs are normalized into `CapabilityResult`.
- Failures become structured state.

Execution results must be attached to the run ledger before the loop continues.

### 9. `updating_memory`

The system updates typed memory from the result.

Memory update rules:
- Tool results are immutable records.
- Derived summaries can be replaced, but raw tool artifacts remain.
- Evidence freshness must be invalidated after workspace writes.
- Plan state must record why it changed.
- Verification state must record command, exit code, and interpretation.

The loop must never rely only on free-form conversation history to decide what happened.

### 10. `verifying`

Verification runs when required by the current step, task type, or side effect.

Verification happens at several points:
- evidence grounding check before final read-only answer
- stale-context check before patch
- diff safety check after patch
- test/lint/typecheck/build after patch where available
- final completion gate before success response

Verification output should be structured:

```python
@dataclass(frozen=True)
class VerificationDecision:
    gate_name: str
    status: Literal["passed", "failed", "skipped", "blocked"]
    blocking: bool
    evidence_refs: tuple[str, ...]
    failure_summary: str | None
    repair_possible: bool
    recommended_next_action: str | None
```

Rule:
- A blocking failed gate prevents `verified_complete`.

### 11. `composing_response`

The response composer builds the final user-facing output from state, evidence, patch, and verification records.

The composer must include:
- answer or change summary
- relevant evidence
- what was verified
- what was not verified
- blocked conditions if present
- next recommended step if incomplete

The composer must not:
- claim success when blocking gates failed
- hide skipped verification
- invent evidence
- overstate confidence

### 12. `stopped`

The run terminates with a stop reason.

Stop reasons:
- `answered`
- `verified_complete`
- `blocked_permission`
- `blocked_missing_evidence`
- `blocked_verification_failed`
- `blocked_stale_context`
- `blocked_unsafe_action`
- `blocked_user_input_required`
- `budget_exhausted`
- `repeated_state`
- `tool_unavailable`
- `provider_unavailable`
- `internal_error`

Stop reason is part of the product contract. It is not just logging.

## Loop Skeleton

This is conceptual pseudocode, not an implementation plan.

```python
def run_task(task_request: TaskRequest) -> TaskRunResult:
    state = intake(task_request)
    state = route(state)

    while not state.is_stopped:
        enforce_budget(state)
        enforce_repetition_guard(state)

        if state.needs_plan:
            state = plan_or_revise(state)

        if state.needs_evidence:
            state = acquire_evidence(state)
            state = check_sufficiency(state)

        action = decide_next_action(state)
        action = enforce_policy(action, state)

        result = execute_action(action)
        state = update_memory(state, action, result)

        if state.needs_verification:
            state = verify(state)

        state = decide_stop_or_continue(state)

    return compose_response(state)
```

The actual implementation can be different, but the control ownership should stay with the runtime.

## Budget Model

Budgets prevent agentic drift.

Budget dimensions:
- total wall-clock time
- LLM calls
- LLM input tokens
- LLM output tokens
- retrieval calls
- reranking calls
- context builds
- direct file reads
- repo searches
- command executions
- patch attempts
- verification attempts
- plan revisions

Recommended initial defaults by mode:

| Mode | LLM Calls | Retrieval Passes | File Reads | Commands | Patch Attempts | Plan Revisions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `direct_answer` | 1 | 1 | 3 | 0 | 0 | 0 |
| `read_only_multipass` | 3 | 3 | 8 | 0 | 0 | 2 |
| `verification_only` | 3 | 2 | 8 | 3 | 0 | 2 |
| `patch_capable` | 8 | 4 | 12 | 5 | 2 | 3 |

These are starting policies, not hard architecture laws. They should be measured and tuned through evaluation.

The LLM call budget is a cap, not a plan. Deterministic sufficiency checks, routing, policy validation, budget enforcement, and verification interpretation should not consume LLM calls unless the runtime marks the case ambiguous.

Example call accounting for a small patch task:

| Step | LLM Call? | Reason |
| --- | ---: | --- |
| Route task | No | Deterministic classifier selects `patch_capable`. |
| Retrieve/rank/context | No | Service calls only. |
| Initial plan | Yes | Strategic planner identifies target evidence and verification. |
| Sufficiency check | No | Deterministic score passes because target file, evidence freshness, and verification command are known. |
| Patch draft | Yes | LLM drafts minimal diff from fresh file content. |
| Diff inspection | No | Deterministic/tool-backed. |
| Verification command | No | Tool execution. |
| Repair after failed focused test | Yes, if needed | Only if failure is specific and repair budget remains. |
| Final response | Yes | Composer summarizes evidence, diff, and verification. |

Expected normal path:
- 3 LLM calls: plan, patch draft, final response.

Expected one-repair path:
- 4 LLM calls: plan, patch draft, repair, final response.

The 8-call cap leaves room for ambiguity and schema repair without making repeated LLM planning the default.

Budget exhaustion behavior:
- If enough evidence exists, compose a partial answer with budget disclosure.
- If required evidence is missing, stop as `budget_exhausted`.
- If a write task is not verified, stop as incomplete rather than successful.

## Repetition Guard

v4 must detect unproductive loops.

A state is considered repeated when the system attempts the same action class with materially identical inputs and no new evidence, no changed plan, no changed tool result, and no changed failure reason.

The repetition key should include:
- phase
- active plan step
- action type
- normalized action input
- relevant evidence set ids
- last error code
- permission profile
- budget state bucket

Allowed repeated actions:
- retry provider call after transient failure with backoff
- rerun verification after patch changed
- retrieve with changed query or retrieval policy

Disallowed repeated actions:
- same retrieval query with same policy after low sufficiency
- same failed test command without patch or environment change
- same patch after conflict without fresh file content
- same planner request after invalid output without stricter schema/repair prompt

For retrieval actions, parameter differences are not enough to prove progress. The repetition guard should compare evidence content.

Retrieval repetition metrics:
- top-N candidate overlap ratio
- top-N file overlap ratio
- new candidate count
- new high-rank file count
- change in retrieval disagreement
- change in sufficiency decision

Initial rule:
- if two consecutive retrieval passes have top-20 candidate overlap above 0.8 and no improved sufficiency decision, the second pass counts as repeated even when retrieval parameters changed.

This directly prevents a v3-style failure mode where slightly different `top_k` or vector settings produce nearly the same evidence while the loop keeps moving.

Repeated state should stop with `repeated_state`, not silently continue.

## Memory Model

v4 should use typed memory, not vague agent memory.

Memory must be inspectable, serializable, and separated by scope.

## Run Ledger

The run ledger should be the source of truth.

Recommended initial format:

```text
.homllm/runs/<run_id>/
  metadata.json
  task.json
  events.jsonl
  snapshots/
  evidence/
  context/
  commands/
  patches/
  verification/
  response/
```

`events.jsonl` should be append-only. Derived state objects such as `TaskState`, `EvidenceWorkspace`, budget state, verification summaries, and response metadata should be reconstructable from events plus optional snapshots.

Snapshots are allowed for convenience and debugging, but they are derived artifacts. If a snapshot conflicts with the event ledger, the event ledger wins.

Why this matters:
- debugging partial runs
- replaying failures
- comparing benchmark variants
- building future trace UI
- supporting resumability later
- preventing mutable memory objects from becoming inconsistent

## Run Memory

Run memory is short-lived memory for one task.

It contains:
- normalized task
- task state
- plan revisions
- evidence attempts
- context packs
- direct reads
- tool calls
- patch attempts
- verification decisions
- response draft metadata
- stop reason

Run memory is authoritative for the current task.

Run memory must be persisted enough to debug and evaluate behavior after the run.

## Evidence Memory

Evidence memory is the structured subset of run memory that supports claims and actions.

Core object:

```python
@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    source_type: Literal["retrieval", "direct_read", "repo_search", "command_output", "diff", "test_output"]
    source_path: str | None
    symbol: str | None
    line_start: int | None
    line_end: int | None
    content_excerpt: str
    content_hash: str | None
    confidence: float
    freshness: Literal["fresh", "possibly_stale", "stale"]
    acquired_at: str
    acquisition_id: str
```

Evidence memory should support:
- claim-to-evidence mapping
- patch-to-evidence mapping
- stale context detection
- final response citations
- eval inspection

Evidence memory must not support:
- making unsupported claims look supported by vague summaries
- replacing raw evidence artifacts with generated prose only
- hiding low confidence evidence

## Plan Memory

Plan memory records the evolution of the plan.

```python
@dataclass(frozen=True)
class PlanRevision:
    revision: int
    reason: str
    based_on_evidence_ids: tuple[str, ...]
    based_on_error_codes: tuple[str, ...]
    steps: tuple[PlanStep, ...]
    created_at: str
```

Plan revisions are allowed when:
- new evidence changes understanding
- verification fails
- a tool is unavailable
- budget pressure requires narrowing scope
- user instruction changes the target

Plan revisions are not allowed when:
- the system is merely wandering
- the planner wants to avoid a failed gate without addressing it
- the revision drops required verification without explicit justification

## Tool Memory

Tool memory records every service/tool call.

It contains:
- tool name
- normalized input summary
- permission required
- side effect level
- result envelope
- artifacts
- duration
- error code
- retry lineage

Tool memory is the source of truth for what the system did.

The response composer should derive "I ran X" statements from tool memory, not from LLM recollection.

## Patch Memory

Patch memory records write intent, application, and verification.

It contains:
- target files
- pre-change hashes
- patch intent
- applied diff
- post-change hashes
- stale-context checks
- diff inspection
- verification gates
- repair attempts

Patch memory must distinguish:
- drafted patch
- applied patch
- verified patch
- failed patch
- blocked patch

Rule:
- An applied patch without passing required verification is not complete.

## Verification Memory

Verification memory records every gate.

It contains:
- gate name
- gate type
- blocking flag
- status
- command if applicable
- exit code if applicable
- evidence refs
- output artifact refs
- failure summary
- repair recommendation

Verification memory should make it impossible to confuse:
- passed
- failed
- skipped
- unavailable
- blocked by permission

## Repository Memory

Repository memory is derived from the workspace and can outlive a run.

Examples:
- index manifest
- chunk store
- vector table
- symbol graph
- call graph
- file metadata
- benchmark history

Repository memory must be invalidated or marked stale when:
- source files change
- index schema changes
- embedding model changes
- chunking policy changes
- relation extraction policy changes
- index age exceeds freshness policy
- workspace has uncommitted changes after index creation

Repository memory can inform the run, but it cannot override fresh file reads or post-patch diff facts.

## Product/User Memory

Product/user memory is a future feature, not required for early v4.

Possible examples:
- preferred test command
- preferred answer style
- project conventions
- common review checklist

Strict rule:
- User/product memory may influence defaults, but it must never override repository evidence, explicit current user instruction, or verification gates.

## Context Assembly Strategy

The agent loop should not pass all memory into every LLM call.

Each LLM call should receive a purpose-built context frame:

### Planning Frame

Contains:
- user task
- route mode
- permission profile
- available tools
- current evidence summary
- known gaps
- budget state
- previous plan revision if any

Excludes:
- full raw file contents unless needed
- full command logs unless relevant
- unrelated prior evidence

### Evidence Sufficiency Frame

Contains:
- required evidence needs
- retrieved evidence summaries
- direct read summaries
- claim support map
- known gaps

Excludes:
- patch drafts
- unrelated tool telemetry

### Patch Draft Frame

Contains:
- target file content or relevant spans
- patch intent
- coding constraints
- stale-context status
- required verification
- related evidence

Excludes:
- broad retrieval dumps
- unrelated files

### Verification Repair Frame

Contains:
- failed gate
- exact command
- relevant output excerpt
- current diff summary
- related files
- prior repair attempts

Excludes:
- unrelated benchmark telemetry
- unrelated retrieval context

### Response Composition Frame

Contains:
- final task state
- evidence support map
- changes made if any
- verification gates
- blocked/skipped gates
- stop reason

Excludes:
- internal chain-of-thought
- irrelevant raw logs

## Evidence Sufficiency Policy

Sufficiency should be treated as a policy decision with structured output.

Initial strategy:
- deterministic-first
- LLM-assisted only for ambiguous or high-risk cases
- policy-validated before the loop continues

Dimensions:
- topical coverage
- source diversity
- freshness
- claim support
- contradiction detection
- verification availability
- risk level

Example policy:

| Task Type | Minimum Evidence |
| --- | --- |
| `explain` | relevant ranked evidence plus claim support map |
| `review` | relevant file reads or exact diff plus issue evidence |
| `debug` | failure signal plus likely source evidence |
| `implement` | target file content, expected behavior, verification strategy |
| `test` | test target, command, expected failure or coverage gap |

The system should explicitly record when sufficiency is below threshold and why.

Deterministic sufficiency signals should include:
- requested entities covered by evidence
- target files identified
- direct-read freshness for target files
- retrieval/ranking agreement
- source-channel diversity
- claim support count
- unsupported claim count
- known contradiction count
- verification strategy availability

LLM-assisted sufficiency is allowed when:
- the query is semantically complex
- retrieved evidence conflicts
- deterministic signals are near threshold
- a write action depends on interpreting behavior, not just locating files
- the system must decide whether uncertainty is user-visible or blocking

LLM-assisted sufficiency must still return the same structured `SufficiencyDecision` and must be validated by runtime policy.

## Claim Support Map

Every final answer that explains repository behavior should map important claims to evidence.

```python
@dataclass(frozen=True)
class ClaimSupport:
    claim_id: str
    claim_text: str
    evidence_ids: tuple[str, ...]
    support_level: Literal["strong", "partial", "unsupported"]
    notes: str | None
```

Rules:
- Strong claims require evidence.
- Unsupported claims must be removed, softened, or listed as uncertainty.
- For code review findings, each finding must have file/line evidence.
- For patch summaries, claims must be backed by diff and verification memory.

This is central to the HOM-LLM thesis: answers should be grounded by construction, not merely written in a grounded style.

## Staleness and Invalidation

Memory staleness must be explicit.

Events that invalidate evidence:
- file write
- patch application
- external user edit
- branch switch
- index rebuild with different policy
- failed patch conflict

Invalidation rules:
- Evidence from changed files becomes `possibly_stale` or `stale`.
- Retrieved evidence from an index marked `possibly_stale` inherits that freshness unless a direct read confirms the current content hash.
- Context packs containing stale evidence cannot be used for patching.
- Direct file reads after a patch supersede earlier retrieved snippets for edited files.
- Verification results before a patch cannot verify the post-patch state.

Staleness should block unsafe writes, not merely warn.

## Planner and Runtime Contract

The planner proposes. The runtime disposes.

Planner may output:
- plan
- next action proposal
- rationale
- evidence needs
- verification needs
- repair suggestion

Runtime decides:
- whether action is allowed
- whether budget permits it
- whether stale context blocks it
- whether tool exists
- whether verification is required
- whether the run should stop

This separation prevents prompt behavior from becoming system behavior.

## Stop Policy

The loop should stop when any of these is true:

### Successful Stops

`answered`:
- Read-only answer has sufficient evidence.
- Required grounding gate passed or uncertainty is disclosed.

`verified_complete`:
- Patch/write task completed.
- Required verification gates passed.
- Diff has been inspected.
- Final response can truthfully describe the change.

### Blocked Stops

`blocked_permission`:
- Needed action is outside current permission profile.

`blocked_missing_evidence`:
- Required evidence cannot be obtained within available tools/budget.

`blocked_verification_failed`:
- Required verification failed and no safe repair remains.

`blocked_stale_context`:
- Write is unsafe because target files changed or evidence is stale.

`blocked_unsafe_action`:
- Planner requested an action disallowed by security policy.

`blocked_user_input_required`:
- Requirements are ambiguous in a way that cannot be resolved safely.

### Safety Stops

`budget_exhausted`:
- Continuing would exceed configured budgets.

`repeated_state`:
- The loop is not making progress.

`tool_unavailable`:
- Required tool/service is unavailable.

`provider_unavailable`:
- Required model/provider is unavailable and fallback is not allowed or exhausted.

`internal_error`:
- Runtime invariant failed.

## Repair Policy

Repair is allowed, but it must be bounded.

Repair is justified when:
- verification failure is specific
- target files are known
- evidence is fresh
- budget permits another attempt
- patch attempt count has not exceeded limit

Repair is not justified when:
- failure is broad and unexplained
- the system lacks evidence
- same repair already failed
- patch would require unsafe command or permission escalation
- user requirements are contradictory

Repair loop:

```text
failed verification
  -> summarize failure
  -> acquire focused evidence if needed
  -> revise plan
  -> patch or stop
  -> rerun required gate
```

Repair must not downgrade required gates to optional gates just to finish.

## Human Interaction Policy

The system should ask the user only when the answer cannot be safely inferred.

Ask user when:
- permission escalation is needed
- product requirement is ambiguous and affects architecture or behavior
- destructive or broad side effects are required
- two valid approaches have materially different tradeoffs
- verification requires credentials or external systems unavailable to the agent

Do not ask user when:
- evidence can answer the question
- a safe default is already defined by policy
- the issue is a normal tool failure with a known fallback
- asking would merely offload engineering responsibility

This is important for product quality. A useful agent should not constantly ask for decisions it can make safely, but it also must not pretend unsafe decisions are obvious.

## Telemetry Requirements

The loop must emit events for:
- phase changes
- route decisions
- plan creation/revision
- evidence acquisition
- sufficiency decisions
- action decisions
- tool execution
- memory invalidation
- verification gates
- stop decisions
- response composition

Minimum event shape:

```python
@dataclass(frozen=True)
class RunEvent:
    event_id: str
    task_id: str
    phase: str
    event_type: str
    timestamp: str
    summary: dict[str, object]
    artifact_refs: tuple[str, ...]
```

Telemetry should support:
- debugging a single run
- comparing benchmark variants
- measuring token efficiency
- identifying repeated-state failures
- finding low-sufficiency answers
- auditing unsafe action refusal

## Evaluation Implications

The loop design should be evaluated on behavior, not aesthetics.

Metrics:
- task success rate
- token usage
- wall-clock latency
- retrieval passes per task
- LLM calls per task
- direct file reads per task
- command executions per patch task
- patch attempts per task
- verification pass/fail/skipped rates
- blocked-state correctness
- hallucination or unsupported-claim rate
- repeated-state stop rate

Key question:
- Does bounded multi-pass improve hard tasks without making easy tasks expensive?

The answer must come from evaluation runs, not belief.

## Initial Implementation Boundary

When implementation planning begins, the first agent loop milestone should be read-only.

Initial loop capabilities:
- intake
- route
- plan
- retrieve/rank/context
- direct read/search
- sufficiency decision
- grounded response composition
- telemetry
- stop reasons

Explicitly excluded from first loop milestone:
- patch application
- arbitrary command execution
- repair loop
- product/user memory
- long-term autonomous sessions

Reason:
- v4 must first prove that the loop and memory model improve read-only grounding and token discipline before write tools increase risk.

## Architectural Decisions

1. The runtime owns the loop; the LLM does not.
2. Memory is typed and scoped, not free-form.
3. Evidence memory is the foundation for claims and actions.
4. Plans are revisable but every revision must be justified.
5. Tool calls are immutable records.
6. Writes invalidate relevant evidence.
7. Verification can block completion.
8. Repeated-state detection is mandatory for multi-pass.
9. Final responses are composed from state, not from model recollection.
10. Product/user memory is deferred until core correctness is proven.
11. The planner is hybrid: deterministic policy first, LLM strategic planning only when useful.
12. Sufficiency is deterministic-first, with LLM assistance only for ambiguous or high-risk cases.
13. The run ledger is append-only `events.jsonl`; snapshots are derived artifacts.

## Initial Loop Decisions

Initial decisions for implementation planning:

1. Persist run memory as append-only `events.jsonl`, with optional derived snapshots.
2. Use deterministic-first sufficiency with optional LLM judgment for ambiguous/high-risk cases.
3. For benchmark answers, every major behavioral claim should have at least one evidence id; unsupported claims must be removed or marked uncertain.
4. Direct file reads should have their own budget separate from retrieval because they are precise but can become exploratory wandering if overused.
5. The first read-only loop should write machine-readable artifacts only; an interactive trace UI belongs to a later product milestone.

## Current Conclusion

The v4 agent loop should be a bounded state machine around typed memory and evidence, not a generic autonomous loop. Multi-pass behavior is valuable only when each pass has a clear purpose, a measurable budget cost, and a structured stop condition.

The next document should define the write/execute/verify design in detail, including safe patching, command execution, rollback policy, and completion gates.
