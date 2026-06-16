# HOM-LLM v4 Write, Execute, Verify Design

Date: 2026-05-09

## Purpose

This document defines how HOM-LLM v4 should safely modify code, execute commands, verify results, recover from failures, and decide whether a task is complete.

This is the highest-risk part of the v4 architecture. Read-only evidence quality can make HOM-LLM useful, but write and execute capability is what turns it into a coding agent. If this layer is designed poorly, the system will become unsafe, untestable, and difficult to trust.

The write/execute/verify design must preserve the v4 thesis:

> HOM-LLM should be a token-efficient, evidence-first coding agent where RAG provides grounded understanding and bounded agency performs only the actions that evidence and verification justify.

## Design Position

Writing files and running commands are not ordinary tools. They are controlled lifecycle operations.

v4 should not think in terms of:
- "let the model edit files"
- "let the model run shell commands"
- "ask the model if it is done"

v4 should think in terms of:
- evidence-supported patch plans
- sandboxed write execution
- policy-checked command execution
- verification gates that can block completion
- structured repair attempts
- truthful stopped states

The LLM can propose. The runtime must enforce.

## Core Rule

No write or execute action should happen unless all of these are true:

1. The action is supported by current evidence.
2. The action is allowed by the permission profile.
3. The action is allowed by the sandbox policy.
4. The action has a declared side-effect level.
5. The target paths or command scope are validated.
6. The expected verification strategy is known.
7. The result will be recorded as an artifact.
8. The stop or repair behavior is defined before execution.

If any of these are missing, the action should stop as blocked instead of proceeding optimistically.

## Approval Policy vs Sandbox Policy

v4 should treat approval and sandboxing as separate architectural controls.

Approval policy answers:
- When must the system ask the user before proceeding?

Sandbox policy answers:
- What is the system technically allowed to do?

These controls must remain orthogonal.

Examples:

| Approval Policy | Sandbox Policy | Behavior |
| --- | --- | --- |
| `always_ask` | `read_only` | Safe exploration and code review. |
| `ask_for_writes` | `workspace_write` | Practical development with user approval before mutations. |
| `ask_for_execution` | `workspace_write` | Auto-edit allowed, commands require approval. |
| `on_request` | `workspace_write` | Autonomous inside workspace, escalates for blocked actions. |
| `never` | `workspace_write` | Autonomous but still technically constrained. |
| `never` | `full_access` | Dangerous mode, not suitable as default product behavior. |

Do not collapse these into a single "mode" internally. Product UX may expose simple modes, but the runtime should keep approval and sandbox decisions separate.

## Permission Profiles

Permission profiles define what categories of actions the agent may request.

### `ReadOnly`

Allowed:
- retrieve evidence
- rank evidence
- build context packs
- search repository
- read files
- inspect git status
- write run artifacts only

Denied:
- workspace source edits
- command execution
- dependency installation
- network access beyond configured model providers

### `VerifyOnly`

Allowed:
- all `ReadOnly` actions
- allowlisted commands that are expected to be read-only or build/test-only
- write command logs and verification artifacts

Denied:
- source edits
- destructive commands
- dependency installation unless explicitly elevated

### `WorkspaceWrite`

Allowed:
- all `VerifyOnly` actions
- create files inside writable workspace roots
- patch files inside writable workspace roots
- update generated artifacts when task requires it

Required:
- path sandbox check
- stale-context check
- patch manifest
- diff inspection
- task-appropriate verification

### `Elevated`

Allowed only with explicit approval:
- network command execution
- package installation
- migration commands
- commands with broader side effects
- writes outside ordinary source roots
- environment mutation

### `DangerousFullAccess`

This should exist only as an explicit research/developer escape hatch.

Allowed:
- broad filesystem and command access

Required:
- explicit user opt-in
- prominent risk labeling
- complete telemetry

Default product behavior should not depend on this profile.

## Sandbox Layers

Sandboxing should be layered. No single mechanism is sufficient.

```text
Approval Policy
  -> Permission Profile
  -> Sandbox Policy
  -> Tool Registry
  -> Path / Command Validation
  -> Runtime Execution
  -> Artifact Capture
  -> Verification Gates
```

## Filesystem Sandbox

The filesystem sandbox controls which paths can be read or written.

### Read Roots

Read roots may include:
- workspace root
- configured dependency/cache directories
- generated run artifact directory
- explicitly approved external files

### Write Roots

Write roots should be narrower than read roots.

Write roots may include:
- workspace root
- configured generated artifact directories
- v4 run artifact directory
- temporary sandbox directory

Write roots should not include:
- user home directory broadly
- system directories
- package manager global directories
- unrelated repositories
- hidden credential directories

### Path Validation

Every write target must pass canonical path validation.

Required pipeline:

```text
requested_path
  -> reject empty/null/control characters
  -> normalize separators
  -> resolve relative path against approved cwd
  -> resolve symlinks/junctions/reparse points where possible
  -> canonical absolute path
  -> verify path is inside allowed write root
  -> verify path is not excluded by deny rules
  -> verify target type is expected
```

Important Windows considerations:
- directory junctions can escape naive root checks
- symlinks can point outside the workspace
- drive-letter casing must be normalized
- UNC paths should be denied unless explicitly supported
- reserved device names should be denied for writes

Important POSIX considerations:
- symlink escape must be checked
- mount points can cross trust boundaries
- case-sensitive and case-insensitive filesystems differ
- permissions can change between check and write

### Deny Rules

Default deny patterns should include:
- `.git/`
- `.hg/`
- `.svn/`
- `.ssh/`
- credential stores
- virtual environments unless task explicitly targets them
- package manager caches
- OS/system directories
- files outside workspace

These deny rules should be policy-controlled, but not casually disabled.

## Artifact Sandbox

Artifacts are part of the safety model.

The agent should write all runtime artifacts under a controlled run directory.

Example:

```text
.homllm/runs/<run_id>/
  task.json
  state.json
  events.jsonl
  evidence/
  context/
  commands/
  patches/
  verification/
  response/
```

Artifacts include:
- task state
- event ledger
- retrieved candidates
- context packs
- command outputs
- patch drafts
- applied diffs
- verification reports
- final response metadata

Artifact rules:
- artifacts must not be mixed with source edits
- artifacts must have stable references
- command output should be truncated in summaries but preserved in files
- sensitive data redaction policy must be explicit
- artifact writes should not count as source workspace mutation

## Command Sandbox

Shell execution is a high-risk capability.

v4 should not allow arbitrary shell-string execution by default.

### Command Representation

Commands should be structured:

```python
@dataclass(frozen=True)
class CommandRequest:
    argv: tuple[str, ...]
    cwd: str
    timeout_ms: int
    env_overlay: dict[str, str]
    network_policy: str
    expected_side_effect: str
    purpose: str
    related_files: tuple[str, ...]
```

Avoid:

```text
"pytest tests && rm -rf tmp"
```

Prefer:

```python
CommandRequest(
    argv=("pytest", "tests/unit/test_auth.py", "-q"),
    cwd="<workspace>",
    timeout_ms=120000,
    env_overlay={},
    network_policy="disabled",
    expected_side_effect="executes_process",
    purpose="Run focused auth unit tests after patch.",
    related_files=("tests/unit/test_auth.py", "src/auth.py"),
)
```

### Command Allowlist

Commands should be classified before execution.

Initial command categories:
- `test`: `pytest`, `unittest`, `npm test`, `pnpm test`, `go test`, `cargo test`
- `lint`: `ruff`, `eslint`, `flake8`, `mypy`, `tsc`
- `build`: project-specific build commands
- `inspect`: `git status`, `git diff`, `git show`, `rg`, `find` equivalents
- `package_install`: dependency installation, elevated only
- `migration`: database or irreversible changes, elevated only
- `destructive`: delete/reset/clean commands, denied by default

The allowlist should be project-configurable, but command risk classification must remain centralized.

### Command Deny Rules

Deny by default:
- recursive delete
- git reset hard
- git checkout/restore paths without explicit approval
- force push
- credential inspection
- shell profile modification
- global package installation
- background daemon launch without explicit need
- network calls in normal verification
- command strings with shell metacharacters unless explicitly using a shell tool profile

On Windows, deny or elevate:
- PowerShell commands that recursively remove/move files
- shell crossovers that enumerate in PowerShell and delete in `cmd`
- registry edits
- service control commands
- hidden window background processes unless explicitly approved

### Command Environment

Command execution should use a controlled environment.

Default rules:
- fixed `cwd`
- minimal inherited environment
- explicit env overlay
- no automatic credential exposure
- network disabled unless policy allows
- timeout required
- stdout/stderr captured
- exit code captured
- process tree cleanup on timeout

### Command Result

Command output should be structured:

```python
@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    cwd: str
    exit_code: int
    timed_out: bool
    stdout_artifact: ArtifactRef
    stderr_artifact: ArtifactRef
    output_excerpt: str
    duration_ms: int
    sandbox_status: str
    policy_decision: str
```

Important result statuses:
- `success`
- `command_failed`
- `timeout`
- `denied_by_policy`
- `denied_by_sandbox`
- `requires_approval`
- `tool_unavailable`
- `sandbox_escape_attempt`

## Execution Runtime Abstraction

The sandbox contract should not assume one implementation such as Docker.

Possible runtime backends:
- local restricted process
- git worktree execution
- copied workspace execution
- container execution
- remote sandbox
- VM-like executor

The architecture should define the runtime interface first.

```python
@dataclass(frozen=True)
class ExecutionBackend:
    backend_name: str
    os_family: str
    supports_network_policy: bool
    supports_filesystem_write_roots: bool
    supports_process_isolation: bool
    supports_timeout_cleanup: bool
```

Backend selection should be policy-driven.

Initial implementation can be simple, but the contract should allow stronger isolation later.

## Approval and Escalation Flow

Escalation should be explicit and structured.

Escalation is needed when:
- action requires a higher permission profile
- sandbox blocks a command that may be valid with approval
- network is required
- dependency installation is required
- write target is outside ordinary roots
- command has unknown side effects
- verification requires external credentials

Escalation request:

```python
@dataclass(frozen=True)
class ApprovalRequest:
    request_id: str
    task_id: str
    requested_capability: str
    current_permission: str
    requested_permission: str
    reason: str
    risk_summary: str
    exact_action: dict[str, object]
    alternatives: tuple[str, ...]
```

Approval response:

```python
@dataclass(frozen=True)
class ApprovalDecision:
    request_id: str
    approved: bool
    scope: Literal["once", "task", "session"]
    constraints: dict[str, object]
    decided_at: str
```

Rule:
- Approval expands permission only within the approved scope. It should not silently change global defaults.

## Write Lifecycle

Writing should be a lifecycle, not a direct file operation.

```text
evidence acquisition
  -> sufficiency check
  -> patch plan
  -> target path validation
  -> stale-context check
  -> patch draft
  -> patch validation
  -> apply patch
  -> diff inspection
  -> verification
  -> repair or stop
  -> response composition
```

## Patch Plan

Before writing, the system must create a patch plan.

```python
@dataclass(frozen=True)
class PatchPlan:
    patch_plan_id: str
    task_id: str
    intent: str
    target_files: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    expected_behavior: str
    verification_gates: tuple[str, ...]
    risk_flags: tuple[str, ...]
    user_visible_summary: str
```

Patch plan requirements:
- target files are explicit
- evidence supports why these files are relevant
- expected behavior is stated
- verification gates are identified
- risk flags are visible

Patch plan anti-patterns:
- "modify relevant files"
- "fix the bug"
- "update implementation and tests"
- "run appropriate verification"

## Stale-Context Check

Before patch application, the system must verify that its evidence still matches the workspace.

Check:
- target file exists or creation is intended
- pre-change hash matches the file read used for patching
- expected span still exists
- workspace dirty state is understood
- user changes are not overwritten
- evidence from retrieved snippets is not stale

Stale-context result:

```python
@dataclass(frozen=True)
class StaleContextCheck:
    ok: bool
    target_file: str
    expected_hash: str | None
    actual_hash: str | None
    stale_reason: str | None
    required_action: Literal["continue", "refresh", "block"]
```

Rule:
- If stale context affects a write target, patching must stop until evidence is refreshed.

## Patch Draft

The LLM may draft a patch, but the runtime owns validation and application.

Patch draft:

```python
@dataclass(frozen=True)
class PatchDraft:
    patch_draft_id: str
    patch_plan_id: str
    format: Literal["unified_diff", "structured_edit"]
    target_files: tuple[str, ...]
    diff_text: str
    rationale: str
    evidence_ids: tuple[str, ...]
```

Patch draft rules:
- must target only approved files
- must be parseable
- must not include unrelated edits
- must not include generated noise
- must preserve user changes
- should prefer minimal diffs

## Patch Validation

Patch validation happens before application.

Validation checks:
- patch parses
- target files are allowed
- patch does not touch denied paths
- patch applies cleanly
- patch size is within policy
- patch does not include suspicious binary changes
- patch does not modify lockfiles unless intended
- patch does not modify generated files unless intended
- patch does not remove tests without explicit reason

Patch validation failure modes:
- `patch_parse_failed`
- `path_denied`
- `patch_conflict`
- `patch_too_large`
- `unexpected_file_change`
- `binary_change_denied`
- `generated_file_denied`

## Patch Application

Patch application should produce a manifest.

```python
@dataclass(frozen=True)
class PatchManifest:
    patch_id: str
    patch_plan_id: str
    applied: bool
    changed_files: tuple[str, ...]
    created_files: tuple[str, ...]
    deleted_files: tuple[str, ...]
    pre_hashes: dict[str, str]
    post_hashes: dict[str, str]
    diff_artifact: ArtifactRef
    applied_at: str
```

Patch application rules:
- write only through controlled patch tool
- record pre/post hashes
- record exact diff artifact
- update patch memory
- invalidate stale evidence for changed files
- trigger diff inspection

## Full-File Writes

Full-file writes should be rare.

Allowed when:
- creating a new file
- replacing a generated artifact intentionally
- file is small and fully owned by the task
- patch format cannot represent required change safely

Denied or elevated when:
- replacing large source files
- rewriting files with user changes
- changing unknown binary files
- touching many unrelated files

If full-file write is used, it must still produce a diff manifest.

## Delete and Move Operations

Deletes and moves are higher risk than edits.

Delete requires:
- explicit patch plan
- target path validation
- evidence explaining why deletion is correct
- diff inspection
- verification

Move/rename requires:
- source path allowed
- destination path allowed
- import/reference impact considered
- verification strategy

Recursive delete should be denied by default.

## Diff Inspection

After patching, v4 must inspect the diff before verification and response.

Diff inspection should identify:
- changed files
- created/deleted files
- risky changes
- unrelated changes
- generated file changes
- test changes
- dependency/lockfile changes
- configuration changes
- secrets accidentally introduced

Diff inspection output:

```python
@dataclass(frozen=True)
class DiffInspectionReport:
    changed_files: tuple[str, ...]
    summary: str
    risky_changes: tuple[str, ...]
    unrelated_changes: tuple[str, ...]
    secrets_risk: bool
    requires_user_review: bool
    diff_artifact: ArtifactRef
```

Rule:
- If diff inspection finds unrelated or unsafe changes, completion must be blocked or repaired.

## Verification Philosophy

Verification is a gate, not a narrative.

The system should not ask:
- "Does the model believe this is fixed?"

The system should ask:
- "Which gates were required?"
- "Which gates passed?"
- "Which gates failed?"
- "Which gates were skipped?"
- "Can success be claimed truthfully?"

## Verification Gate Types

### `grounding`

Checks whether claims or patch rationale are supported by evidence.

Required for:
- read-only answers
- code review findings
- patch summaries

### `stale_context`

Checks whether write evidence still matches target files.

Required before:
- patch application
- full-file write
- delete
- move

### `diff_safety`

Checks whether the produced diff is scoped and safe.

Required after:
- any workspace write

### `syntax`

Checks parse/compile-level correctness when available.

Examples:
- Python AST parse
- TypeScript compile
- Rust check
- Go test compile phase

### `unit_test`

Runs focused unit tests.

Required when:
- relevant tests are discoverable
- task changes behavior covered by tests

### `integration_test`

Runs broader tests where justified.

Required when:
- behavior crosses subsystem boundaries
- focused tests are insufficient

### `lint`

Runs formatting or lint checks.

Required when:
- project policy requires it
- changed files are in linted paths

### `typecheck`

Runs static type checks where available.

Required when:
- project has typecheck command
- task modifies typed code paths

### `build`

Runs build command where needed.

Required when:
- patch affects build configuration
- no narrower verification exists

### `manual_review`

Marks cases where automated verification is insufficient.

Required when:
- UI behavior cannot be tested automatically
- credentials/external systems are unavailable
- task requires subjective product judgment

## Verification Plan

Before patching, the system must define a verification plan.

```python
@dataclass(frozen=True)
class VerificationPlan:
    verification_plan_id: str
    task_id: str
    required_gates: tuple[str, ...]
    optional_gates: tuple[str, ...]
    commands: tuple[CommandRequest, ...]
    skip_policy: dict[str, str]
    success_criteria: tuple[str, ...]
```

Skip policy must be explicit.

Valid skip reasons:
- command unavailable
- dependency missing
- external service unavailable
- user declined approval
- no relevant tests exist
- budget exhausted before optional gate

Invalid skip reasons:
- command might fail
- gate is inconvenient
- model confidence is high
- patch seems small

## Verification Result

Each gate returns a structured result.

```python
@dataclass(frozen=True)
class VerificationGateResult:
    gate_id: str
    gate_type: str
    blocking: bool
    status: Literal["passed", "failed", "skipped", "blocked"]
    command_result_id: str | None
    evidence_ids: tuple[str, ...]
    artifact_refs: tuple[ArtifactRef, ...]
    summary: str
    failure_reason: str | None
    repair_hint: str | None
```

Final verification decision:

```python
@dataclass(frozen=True)
class VerificationSummary:
    required_passed: bool
    failed_blocking_gates: tuple[str, ...]
    skipped_blocking_gates: tuple[str, ...]
    optional_failures: tuple[str, ...]
    can_claim_success: bool
    completion_status: str
```

Rule:
- `can_claim_success` must be false if any blocking gate failed, was skipped without acceptable reason, or was blocked.

## Completion Policy

Completion is a runtime decision.

`verified_complete` requires:
- patch applied or no patch needed
- diff inspected
- required gates passed
- no unresolved stale context
- no unrelated risky changes
- response can cite evidence and verification

`answered` requires:
- sufficient evidence
- important claims supported
- uncertainty disclosed
- no required write/execute action left undone

`blocked_verification_failed` requires:
- at least one blocking gate failed
- repair is unavailable, unsafe, or budget-exhausted

`blocked_missing_evidence` requires:
- required evidence could not be acquired
- continuing would repeat or exceed budget

`blocked_permission` requires:
- needed action requires approval or higher permission
- no safe lower-permission alternative exists

## Repair Policy

Repair attempts should be allowed but bounded.

Repair is allowed when:
- failure is specific
- evidence is fresh
- target files are known
- patch scope remains small
- budget permits
- repair attempt count remains within policy

Repair is denied when:
- failure is broad and unexplained
- same repair already failed
- stale context is unresolved
- repair requires unsafe command
- repair requires unapproved escalation
- patch scope would expand beyond the original task

Repair lifecycle:

```text
verification failed
  -> classify failure
  -> map failure to changed files or evidence gaps
  -> acquire focused evidence if needed
  -> revise patch plan
  -> apply repair patch
  -> inspect diff
  -> rerun failed gate and dependent gates
```

Repair limits should be mode-specific.

Recommended initial limits:
- `VerifyOnly`: 0 patch repairs
- `WorkspaceWrite`: 2 patch attempts
- `Elevated`: explicit approval per broad repair

## Rollback Policy

Rollback is recovery, not sandboxing.

v4 should not depend on rollback as the primary safety mechanism. The sandbox should prevent unsafe actions before they occur.

Rollback is useful when:
- patch applies but verification fails
- user asks to undo agent changes
- diff inspection finds unrelated changes from the agent
- repair would be riskier than reverting

Rollback requires:
- patch manifest
- pre-change hashes
- knowledge of user changes after patch
- safe reverse patch

Rollback must not:
- remove user changes made after the agent patch
- run destructive git commands without explicit approval
- hide the fact that rollback happened

Preferred rollback mechanism:
- reverse the agent's patch using the patch manifest

Avoid by default:
- `git reset --hard`
- broad checkout/restore commands
- recursive cleanup

## Dirty Workspace Policy

v4 must handle dirty workspaces carefully.

At task start:
- inspect git status when available
- record pre-existing changed files
- distinguish user changes from agent changes

Before patch:
- block if target file has changed since evidence acquisition
- do not overwrite unrelated user changes

After patch:
- diff inspection must identify agent changes
- response must not claim ownership of pre-existing changes

If workspace is not a git repo:
- use file hashes and patch manifests
- avoid broad operations that require version control
- disclose reduced rollback capability

## Dependency Installation Policy

Dependency installation is elevated.

Reasons:
- network access
- lockfile mutation
- environment mutation
- supply-chain risk
- slow and nondeterministic behavior

Allowed only when:
- task requires it
- user approves
- package manager and target files are identified
- lockfile changes are expected
- verification plan includes post-install checks

Denied by default:
- global installs
- unpinned dependency additions where project convention requires pins
- install scripts in unsafe contexts
- dependency changes unrelated to task

## Network Policy

Network access should be disabled for command execution by default.

Allowed network cases:
- configured LLM providers
- approved package installation
- approved external API tests
- approved documentation fetch

Network policy values:
- `disabled`
- `model_providers_only`
- `approved_hosts`
- `unrestricted_elevated`

Verification that depends on network should be marked as such.

## RAG Role In Write Tasks

RAG should reduce wandering before patching.

For write tasks, RAG should provide:
- candidate target files
- relevant symbols
- call graph/context edges
- existing patterns
- likely tests
- related configuration
- risk surfaces

RAG should not replace:
- fresh target file reads before patching
- stale-context checks
- diff inspection
- verification execution

Correct flow:

```text
RAG finds likely evidence
  -> direct read confirms exact current content
  -> planner creates patch plan
  -> patch uses fresh content
  -> verification proves result
```

Incorrect flow:

```text
RAG snippet looks relevant
  -> model patches based on snippet
  -> response claims success without fresh read or tests
```

## Test Discovery

v4 should discover verification options before patching where possible.

Sources:
- repository config
- package files
- CI config
- existing test directories
- imports and file naming
- historical eval/run metadata
- user-provided commands

Test discovery output:

```python
@dataclass(frozen=True)
class VerificationCandidate:
    gate_type: str
    command: CommandRequest | None
    confidence: float
    related_files: tuple[str, ...]
    reason: str
```

The system should prefer focused tests first, then broader gates if needed.

## Verification Selection Policy

Verification should be proportional to risk.

Low-risk doc/comment change:
- diff safety
- optional lint/spell if configured

Small pure function change:
- focused unit test
- syntax/typecheck if available
- diff safety

Cross-module behavior change:
- focused unit test
- related integration test
- typecheck/build if available
- diff safety

Dependency/config change:
- install/build/test commands as approved
- lockfile inspection
- diff safety

Large refactor:
- broad tests
- typecheck/build
- stricter diff inspection
- likely user review gate

## Failure Classification

Failures should be classified before repair.

Failure classes:
- `syntax_error`
- `type_error`
- `test_assertion_failure`
- `missing_dependency`
- `command_unavailable`
- `environment_failure`
- `timeout`
- `permission_denied`
- `sandbox_denied`
- `network_required`
- `stale_context`
- `patch_conflict`
- `unknown`

Repair strategy should depend on failure class.

Examples:
- `syntax_error`: inspect changed files and fix syntax.
- `test_assertion_failure`: map failing test to behavior and revise patch.
- `missing_dependency`: ask for approval if installation is justified.
- `environment_failure`: block or ask user; do not edit code blindly.
- `sandbox_denied`: ask for approval or choose lower-risk alternative.
- `timeout`: narrow command or increase timeout only if safe.

## Safety Invariants

The runtime should enforce these invariants:

1. No write without permission and sandbox approval.
2. No command execution without command policy decision.
3. No patch without fresh target context.
4. No success claim after blocking verification failure.
5. No silent escalation.
6. No hidden fallback from failed verification to confident answer.
7. No mutation outside allowed write roots.
8. No destructive command in normal mode.
9. No rollback that destroys user changes.
10. No final answer that hides skipped required gates.

These invariants should become contract tests when implementation begins.

## Telemetry Requirements

Write/execute/verify telemetry must capture:
- permission profile
- approval policy
- sandbox policy
- path decisions
- command policy decisions
- approval requests and responses
- patch plans
- stale-context checks
- patch manifests
- diff inspections
- verification plans
- verification results
- repair attempts
- rollback attempts
- final completion decision

Telemetry should answer:
- Why was this action allowed?
- What did it change?
- What verified it?
- What failed?
- Was escalation requested?
- Did the sandbox block anything?
- Can the result be reproduced?

## Evaluation Requirements

The write/execute/verify layer should be evaluated separately from answer quality.

Metrics:
- patch success rate
- verification pass rate
- false success rate
- blocked-state correctness
- average patch attempts
- command executions per task
- token usage before patch
- token usage after failure
- stale-context block rate
- sandbox denial correctness
- rollback success rate
- unrelated diff rate

Benchmarks should include:
- simple single-file fix
- multi-file behavior change
- failing test repair
- stale-context simulation
- dirty workspace simulation
- command unavailable simulation
- permission denied simulation
- patch conflict simulation
- verification failure requiring repair
- verification failure requiring stop

The system should be rewarded for truthful blocking when success is unsafe.

## Product UX Requirements

If v4 becomes product-facing, users should see:
- current mode
- approval policy
- sandbox policy
- planned writes
- planned commands
- verification gates
- blocked reasons
- final diff summary
- verification summary

The product should not expose every internal event by default, but the trace should be inspectable.

Useful UX states:
- "Reading evidence"
- "Planning patch"
- "Waiting for approval"
- "Applying patch"
- "Running focused tests"
- "Repairing failed verification"
- "Blocked: permission required"
- "Blocked: verification failed"
- "Complete: verified"

## Initial Implementation Boundary

When implementation planning begins, write/execute/verify should not be built all at once.

Recommended sequence:

1. Implement sandbox and approval policy models without executing commands.
2. Implement path validation and artifact sandbox.
3. Implement diff inspection over existing workspace changes.
4. Implement verification planning without command execution.
5. Implement allowlisted read-only command execution.
6. Implement structured command results and verification gates.
7. Implement patch planning and stale-context checks.
8. Implement patch application with manifest.
9. Implement post-patch diff inspection and focused verification.
10. Implement bounded repair.
11. Implement rollback only after patch manifests are reliable.

Reason:
- The safety substrate must exist before write capability.

## Architectural Decisions

1. Approval policy and sandbox policy are separate controls.
2. Shell execution is a high-risk capability, not a normal tool.
3. Patch-based editing is the default write mechanism.
4. Full-file writes, deletes, moves, installs, network, and destructive actions require stricter policy.
5. Path canonicalization and write-root checks are mandatory.
6. Artifacts are part of the safety and audit model.
7. Verification gates decide completion, not model confidence.
8. Repair is bounded and evidence-driven.
9. Rollback is recovery, not the main safety mechanism.
10. RAG guides what to change, but fresh reads and verification prove it.

## Open Architectural Questions

These should be resolved before implementation planning:

1. Should the first execution backend be local restricted process or git worktree based?
2. Should `.homllm/runs/` be the default artifact directory, or should artifacts live outside the repository by default?
3. What command allowlist should be enabled for the first `VerifyOnly` milestone?
4. Should dependency installation be completely unsupported until product approval UX exists?
5. Should rollback be included in the first patch-capable milestone, or should failed verification initially stop without rollback?
6. How strict should dirty-workspace blocking be for files that are unrelated to the patch target?

## Current Conclusion

v4 should not add write tools as a simple extension of the current read-only system. Writing and execution require a safety substrate: approval policy, sandbox policy, path validation, command policy, artifact capture, patch manifests, diff inspection, and verification gates.

The next document should define the migration and validation plan: how v4 is built beside v3, which milestones prove value, and which evaluations decide whether the system moves toward a product track.
