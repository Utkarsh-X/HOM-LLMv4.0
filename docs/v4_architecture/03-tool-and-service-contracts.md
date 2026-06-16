# HOM-LLM v4 Tool and Service Contracts

Date: 2026-05-09

## Purpose

This document defines the contract discipline for HOM-LLM v4 services and tools. It exists to prevent the v4 architecture from becoming a vague agent loop with arbitrary functions attached.

Every service and tool must be typed, permissioned, auditable, and testable. If a capability cannot define its inputs, outputs, side effects, failure modes, and telemetry, it should not be part of v4.

## Contract Philosophy

v4 should separate two kinds of capabilities:

1. **Services**
   - Long-lived or composable system capabilities.
   - Examples: indexing, retrieval, ranking, context packing, verification.
   - Usually called by the orchestrator or planner.

2. **Tools**
   - Discrete actions the agent can invoke.
   - Examples: read file, search repo, run tests, apply patch.
   - Always permission-checked.

Services can be implemented using tools internally, but their public contract should stay stable.

## Architectural Tiers

v4 should separate runtime law from execution services and advisory intelligence.

### Tier A: Core Runtime Law

These objects are mandatory and should not be optional plugins:
- `Task`
- `TaskState`
- `CapabilityPolicy`
- `CapabilityResult`
- `EvidenceWorkspace`
- `VerificationGate`
- budget enforcement
- stop reasons
- run ledger events

Tier A defines what the runtime is allowed to do.

### Tier B: Core Services

These services are required for normal v4 execution:
- `IndexService`
- `EvidenceRetrievalService`
- `EvidenceRankingService`
- `ContextPackService`
- `DirectReadService`
- `PlannerService`
- `VerificationService`

Tier B services may degrade, but the degraded state must be explicit.

### Tier C: Advisory Intelligence

These capabilities can improve quality but should not block early runtime progression:
- advanced hallucination signals
- stylistic quality scoring
- readability scoring
- optional answer polish checks
- experimental ranking heuristics

Tier C outputs can inform decisions, but Tier A policy decides whether a run may continue.

## Capability Policy

Policy should be centralized instead of scattered across router, planner, tools, and verification.

```python
@dataclass(frozen=True)
class CapabilityPolicy:
    permission_profile: str
    approval_policy: str
    sandbox_policy: str
    allowed_tools: tuple[str, ...]
    blocked_tools: tuple[str, ...]
    verification_requirements: tuple[str, ...]
    budget_caps: dict[str, int]
    escalation_rules: tuple[str, ...]
```

Runtime responsibilities:
- derive the initial policy during task intake/routing
- pass policy into planner and tool execution
- reject planner actions that violate policy
- record policy changes in the run ledger

Planner responsibilities:
- propose actions inside the current policy
- request escalation when policy blocks a necessary action
- never mutate policy directly

## Universal Contract Fields

Every service/tool contract must specify:

- `name`
- `purpose`
- `input_schema`
- `output_schema`
- `permission_required`
- `side_effect_level`
- `idempotency`
- `timeout_policy`
- `retry_policy`
- `failure_modes`
- `telemetry`
- `artifacts`
- `verification_requirements`
- `security_notes`

## Permission Levels

### `none`

No workspace access. Pure classification, formatting, validation, or planning.

### `read_workspace`

Can inspect repository files and artifacts. Cannot execute commands or write files.

### `execute_readonly`

Can run allowlisted commands that should not modify workspace state.

### `write_workspace`

Can create, edit, or delete files through controlled patch/write APIs.

### `external_network`

Can call external services beyond configured LLM providers. This should be rare.

### `dangerous`

Can perform operations with broad or destructive side effects. This should not be available in normal v4 operation.

## Side-Effect Levels

### `pure`

No side effects. Same input should produce equivalent output.

### `read_only`

Reads local state but does not modify it.

### `writes_artifacts`

Writes telemetry, caches, indexes, or run artifacts, but not user source files.

### `writes_workspace`

Modifies user workspace files.

### `executes_process`

Runs a local process.

### `external_call`

Calls an external service.

### `destructive`

Can delete, reset, overwrite, or otherwise risk user work.

## Common Result Envelope

Every service/tool should return a result envelope.

```python
@dataclass(frozen=True)
class CapabilityResult[T]:
    capability_name: str
    ok: bool
    output: T | None
    error: CapabilityError | None
    telemetry: CapabilityTelemetry
    artifacts: tuple[ArtifactRef, ...]
```

### `CapabilityError`

```python
@dataclass(frozen=True)
class CapabilityError:
    code: str
    message: str
    recoverable: bool
    retryable: bool
    details: dict[str, object]
```

Error codes should be stable strings, not arbitrary exception messages.

Examples:
- `index_missing`
- `index_stale`
- `permission_denied`
- `file_not_found`
- `parse_failed`
- `command_failed`
- `patch_conflict`
- `verification_failed`
- `timeout`
- `provider_unavailable`

### `CapabilityTelemetry`

```python
@dataclass(frozen=True)
class CapabilityTelemetry:
    started_at: str
    ended_at: str
    duration_ms: int
    input_summary: dict[str, object]
    output_summary: dict[str, object]
    token_usage: dict[str, int]
    model_usage: dict[str, object]
    degraded: bool
    degradation_reason: str | None
```

Telemetry should be useful for evaluation and debugging without exposing unnecessary full payloads in summaries.

### `ArtifactRef`

```python
@dataclass(frozen=True)
class ArtifactRef:
    artifact_type: str
    path: str
    description: str
    content_hash: str | None
```

Artifact examples:
- telemetry JSON
- retrieved candidate dump
- context pack JSON
- command output
- patch diff
- verification report

## Service Contracts

### 1. `IndexService`

Purpose:
- Build, load, validate, and describe repository index artifacts.

Permission required:
- `read_workspace`

Side-effect level:
- `writes_artifacts` when indexing
- `read_only` when validating/loading

Input schema:

```python
@dataclass(frozen=True)
class IndexRequest:
    workspace_root: str
    include_patterns: tuple[str, ...]
    exclude_patterns: tuple[str, ...]
    language_profile: str
    mode: Literal["load", "validate", "rebuild", "incremental"]
    max_index_age_seconds: int | None = None
    force: bool = False
```

Output schema:

```python
@dataclass(frozen=True)
class RepoIndexManifest:
    index_id: str
    workspace_root: str
    schema_version: str
    created_at: str
    last_indexed_at: str
    source_file_count: int
    chunk_count: int
    symbol_count: int
    relation_count: int
    embedding_model: str
    embedding_dimension: int
    artifact_paths: dict[str, str]
    ignored_paths_summary: dict[str, int]
    warnings: tuple[str, ...]
```

```python
@dataclass(frozen=True)
class IndexFreshness:
    status: Literal["fresh", "possibly_stale", "stale"]
    reason: str | None
    indexed_at: str
    workspace_changed_since_index: bool
    stale_file_count: int
    untracked_file_count: int
```

The manifest or validation result must expose index freshness before retrieval uses indexed evidence.

Failure modes:
- `workspace_missing`
- `index_missing`
- `index_stale`
- `schema_mismatch`
- `embedding_dimension_mismatch`
- `index_build_failed`

Telemetry:
- files scanned
- files indexed
- ignored files
- chunks created
- symbols extracted
- relations extracted
- vector count
- duration by stage

Verification requirements:
- Manifest must exist before retrieval tools use the index.
- Schema version must match v4 compatibility policy.
- Embedding dimension must match vector table dimension.
- If the workspace changed since indexing, retrieved evidence from affected files must be marked `possibly_stale`.
- If the index exceeds `max_index_age_seconds`, retrieval may continue only in degraded mode unless policy requires a fresh index.

Design note:
- v3 indexing is reusable, but v4 should require explicit manifest validation before evidence acquisition.

### 2. `EvidenceRetrievalService`

Purpose:
- Acquire repository evidence using indexed retrieval channels.

Permission required:
- `read_workspace`

Side-effect level:
- `read_only`

Input schema:

```python
@dataclass(frozen=True)
class RetrievalPolicy:
    bm25_top_k: int
    vector_top_k: int
    graph_enabled: bool
    graph_max_depth: int
    precision_recovery_enabled: bool
    coverage_recovery_enabled: bool
    vector_mode: Literal["off", "lite", "balanced", "broad"]
    retrieval_scope: Literal["narrow", "balanced", "discovery"]
```

```python
@dataclass(frozen=True)
class EvidenceRetrievalRequest:
    task_id: str
    query: str
    task_class: str
    index_id: str
    policy: RetrievalPolicy
    target_files: tuple[str, ...] = ()
    target_symbols: tuple[str, ...] = ()
```

Output schema:

```python
@dataclass(frozen=True)
class EvidenceCandidate:
    candidate_id: str
    file_path: str
    symbol_id: str | None
    span_start: int | None
    span_end: int | None
    content_hash: str
    source_channels: tuple[str, ...]
    bm25_score: float | None
    vector_score: float | None
    graph_score: float | None
    retrieval_score: float
    metadata: dict[str, object]
```

```python
@dataclass(frozen=True)
class EvidenceSet:
    evidence_set_id: str
    query: str
    candidates: tuple[EvidenceCandidate, ...]
    diagnostics: RetrievalDiagnostics
```

```python
@dataclass(frozen=True)
class RetrievalDiagnostics:
    bm25_count: int
    vector_count: int
    graph_added_count: int
    precision_added_count: int
    coverage_added_count: int
    retrieval_disagreement: float | None
    degraded: bool
    degradation_reason: str | None
```

Failure modes:
- `index_missing`
- `index_stale`
- `bm25_failed`
- `vector_failed`
- `graph_unavailable`
- `no_candidates`

Telemetry:
- per-channel counts
- per-channel latency
- final candidate count
- disagreement metrics
- degraded mode

Verification requirements:
- If all channels fail, output must be `ok=False`.
- If one channel fails but others work, output may be `ok=True` with `degraded=True`.

Design note:
- The recent vector canary proves v4 needs explicit retrieval policies. Broad vector should be a planner choice, not a hidden default.

### 3. `EvidenceRankingService`

Purpose:
- Rank and score evidence candidates for the task.

Permission required:
- `read_workspace`

Side-effect level:
- `read_only`

Input schema:

```python
@dataclass(frozen=True)
class RankingPolicy:
    reranker_enabled: bool
    reranker_model: str
    reranker_top_m: int
    bm25_weight: float
    dense_weight: float
    name_weight: float
    structural_weight: float
    bm25_rescue_top_k: int
```

```python
@dataclass(frozen=True)
class EvidenceRankingRequest:
    task_id: str
    evidence_set: EvidenceSet
    policy: RankingPolicy
```

Output schema:

```python
@dataclass(frozen=True)
class RankedEvidence:
    candidate: EvidenceCandidate
    rank: int
    final_score: float
    score_components: dict[str, float]
    reranked: bool
```

```python
@dataclass(frozen=True)
class RankedEvidenceSet:
    ranked_set_id: str
    items: tuple[RankedEvidence, ...]
    diagnostics: RankingDiagnostics
```

```python
@dataclass(frozen=True)
class RankingDiagnostics:
    reranker_used: bool
    reranker_available: bool
    reranker_degraded_reason: str | None
    concentration_ratio: float | None
    score_separation: float | None
    top_source_channels: dict[str, int]
```

Failure modes:
- `empty_evidence_set`
- `reranker_unavailable`
- `feature_extraction_failed`
- `ranking_failed`

Telemetry:
- reranker latency
- reranked count
- score variance
- top files
- source-channel distribution

Verification requirements:
- Reranker unavailability must be visible.
- Ranking must preserve candidate provenance.

### 4. `ContextPackService`

Purpose:
- Convert ranked evidence into task-purpose-specific context packs.

Permission required:
- `read_workspace`

Side-effect level:
- `read_only`

Input schema:

```python
@dataclass(frozen=True)
class ContextPolicy:
    purpose: Literal["answer", "planning", "patching", "verification", "failure_analysis"]
    max_tokens: int
    citation_style: Literal["file", "file_line", "symbol"]
    preserve_top_n: int
    allow_summarization: bool
    include_drop_ledger: bool
```

```python
@dataclass(frozen=True)
class ContextPackRequest:
    task_id: str
    ranked_evidence_set: RankedEvidenceSet
    policy: ContextPolicy
```

Output schema:

```python
@dataclass(frozen=True)
class ContextBlock:
    block_id: str
    candidate_id: str
    file_path: str
    span_start: int | None
    span_end: int | None
    text: str
    token_count: int
    score: float
    citation: str
```

```python
@dataclass(frozen=True)
class ContextPack:
    context_pack_id: str
    purpose: str
    text: str
    blocks: tuple[ContextBlock, ...]
    used_tokens: int
    dropped_candidates: tuple[str, ...]
    diagnostics: ContextDiagnostics
```

Failure modes:
- `empty_ranked_evidence`
- `token_budget_too_small`
- `context_pack_failed`

Telemetry:
- blocks selected
- tokens used
- files represented
- dropped candidates
- top-file concentration
- retrieval disagreement inherited from evidence

Verification requirements:
- Context pack must include provenance for every block.
- If the context is insufficient for the requested purpose, diagnostics must say so.

### 5. `DirectReadService`

Purpose:
- Read current workspace file content for precise evidence and stale-context validation.

Permission required:
- `read_workspace`

Side-effect level:
- `read_only`

Input schema:

```python
@dataclass(frozen=True)
class DirectReadRequest:
    task_id: str
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    max_bytes: int = 20000
    require_hash: bool = True
```

Output schema:

```python
@dataclass(frozen=True)
class DirectReadResult:
    file_path: str
    content_excerpt: str
    line_start: int | None
    line_end: int | None
    content_hash: str | None
    truncated: bool
    freshness: Literal["fresh", "possibly_stale", "stale"]
```

Failure modes:
- `file_not_found`
- `path_denied`
- `file_too_large`
- `binary_file_denied`
- `read_failed`

Telemetry:
- bytes read
- truncation status
- path validation result
- content hash presence

Verification requirements:
- Direct reads used for patching must include a content hash.
- Direct reads supersede retrieved snippets for the same file when freshness differs.

### 6. `PlannerService`

Purpose:
- Produce and revise bounded task plans.

Permission required:
- `none`

Side-effect level:
- `pure` or `external_call` if LLM-backed

Input schema:

```python
@dataclass(frozen=True)
class PlannerRequest:
    task: Task
    task_state: TaskState
    capability_policy: CapabilityPolicy
    evidence_summary: dict[str, object]
    available_tools: tuple[str, ...]
    budget_state: dict[str, object]
    planner_mode: Literal["deterministic", "llm_strategic", "repair"]
```

Output schema:

```python
@dataclass(frozen=True)
class PlannerDecision:
    action: Literal["answer", "retrieve", "read", "execute", "patch", "verify", "ask_user", "stop"]
    rationale: str
    tool_name: str | None
    tool_input: dict[str, object]
    required_gates: tuple[str, ...]
    confidence: float
```

Failure modes:
- `planner_parse_failed`
- `unsafe_action_requested`
- `budget_exhausted`
- `no_valid_action`

Telemetry:
- LLM tokens if model-backed
- parse corrections
- selected action
- rejected unsafe action count

Verification requirements:
- Planner output must be schema-validated before execution.
- Planner cannot bypass permission checks.
- Planner cannot change `CapabilityPolicy`; it may only request escalation.
- Deterministic policy validation must run after every planner decision.

Design note:
- v4 should use a hybrid planner. Deterministic routing and policy decide common flow; an LLM-backed strategic planner is used for decomposition, ambiguity, and repair. The LLM planner should not run on every loop iteration by default.

### 7. `VerificationService`

Purpose:
- Evaluate whether an answer, plan, patch, or task state satisfies required gates.

Permission required:
- depends on gate type

Side-effect level:
- `read_only` or `executes_process`

Input schema:

```python
@dataclass(frozen=True)
class VerificationRequest:
    task_id: str
    gate_names: tuple[str, ...]
    evidence_workspace_id: str
    patch_manifest_id: str | None
    command_policy: dict[str, object]
```

Output schema:

```python
@dataclass(frozen=True)
class VerificationGateResult:
    gate_name: str
    status: Literal["passed", "failed", "skipped", "blocked"]
    blocking: bool
    summary: str
    evidence: dict[str, object]
    artifacts: tuple[ArtifactRef, ...]
```

```python
@dataclass(frozen=True)
class VerificationReport:
    report_id: str
    gates: tuple[VerificationGateResult, ...]
    completion_allowed: bool
    repair_recommended: bool
```

Failure modes:
- `gate_unknown`
- `command_not_allowed`
- `verification_command_failed`
- `verification_artifact_missing`

Telemetry:
- gates requested
- gates passed/failed/skipped
- command durations
- exit codes
- blocking failures

Verification requirements:
- Required gates must block completion if failed or blocked.
- Skipped required gates must be visible and usually blocking.

## Tool Contracts

### 1. `retrieve_evidence`

Service-backed tool:
- Calls `EvidenceRetrievalService`.

Permission:
- `read_workspace`

Side effect:
- `read_only`

Use when:
- the agent needs repository evidence for a task.

Do not use when:
- exact file path and line are already known and current file content is required.

### 2. `rank_evidence`

Service-backed tool:
- Calls `EvidenceRankingService`.

Permission:
- `read_workspace`

Side effect:
- `read_only`

Use when:
- raw retrieval candidates need priority ordering.

### 3. `build_context_pack`

Service-backed tool:
- Calls `ContextPackService`.

Permission:
- `read_workspace`

Side effect:
- `read_only`

Use when:
- the LLM needs a compact evidence packet for answer, plan, patch, or verification.

### 4. `search_repo`

Purpose:
- Deterministic lexical search over repository files.

Permission:
- `read_workspace`

Side effect:
- `read_only`

Input schema:

```python
@dataclass(frozen=True)
class SearchRepoInput:
    pattern: str
    path_globs: tuple[str, ...]
    case_sensitive: bool
    max_results: int
```

Output schema:

```python
@dataclass(frozen=True)
class SearchHit:
    file_path: str
    line_number: int
    line_text: str
    match_span: tuple[int, int] | None
```

Failure modes:
- `invalid_pattern`
- `search_timeout`
- `too_many_results`

Rule:
- Search results are evidence hints, not final context. Important hits should be read or packed before generation.

### 5. `read_file`

Purpose:
- Read exact file content or spans.

Permission:
- `read_workspace`

Side effect:
- `read_only`

Input schema:

```python
@dataclass(frozen=True)
class ReadFileInput:
    file_path: str
    start_line: int | None
    end_line: int | None
    max_bytes: int
```

Output schema:

```python
@dataclass(frozen=True)
class ReadFileOutput:
    file_path: str
    content: str
    start_line: int
    end_line: int
    content_hash: str
    truncated: bool
```

Failure modes:
- `file_not_found`
- `path_outside_workspace`
- `file_too_large`
- `decode_failed`

Verification requirements:
- Patch tools must use content hashes or equivalent stale-context checks.

### 6. `run_command`

Purpose:
- Run allowlisted local commands for inspection or verification.

Permission:
- `execute_readonly`

Side effect:
- `executes_process`

Input schema:

```python
@dataclass(frozen=True)
class RunCommandInput:
    command: tuple[str, ...]
    cwd: str
    timeout_ms: int
    purpose: Literal["test", "lint", "typecheck", "build", "inspect"]
```

Output schema:

```python
@dataclass(frozen=True)
class RunCommandOutput:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
```

Failure modes:
- `command_not_allowed`
- `timeout`
- `nonzero_exit`
- `cwd_invalid`

Rules:
- Commands must be structured as argv tuples, not shell strings.
- Destructive commands are not allowed in normal profiles.
- Nonzero exit is not a tool crash; it is a command result that verification may interpret.

### 7. `apply_patch`

Purpose:
- Apply controlled patches to workspace files.

Permission:
- `write_workspace`

Side effect:
- `writes_workspace`

Input schema:

```python
@dataclass(frozen=True)
class PatchOperation:
    file_path: str
    expected_content_hash: str | None
    patch_text: str
```

```python
@dataclass(frozen=True)
class ApplyPatchInput:
    operations: tuple[PatchOperation, ...]
    reason: str
```

Output schema:

```python
@dataclass(frozen=True)
class PatchManifest:
    manifest_id: str
    changed_files: tuple[str, ...]
    added_files: tuple[str, ...]
    deleted_files: tuple[str, ...]
    diff_path: str
    pre_hashes: dict[str, str]
    post_hashes: dict[str, str]
```

Failure modes:
- `permission_denied`
- `stale_context`
- `patch_conflict`
- `path_outside_workspace`
- `patch_apply_failed`

Verification requirements:
- Patch application must be followed by diff inspection and task-appropriate verification before success.

### 8. `inspect_diff`

Purpose:
- Summarize workspace changes after patching.

Permission:
- `read_workspace`

Side effect:
- `read_only`

Input schema:

```python
@dataclass(frozen=True)
class InspectDiffInput:
    base_ref: str | None
    include_untracked: bool
    max_bytes: int
```

Output schema:

```python
@dataclass(frozen=True)
class DiffInspection:
    changed_files: tuple[str, ...]
    summary: str
    risky_changes: tuple[str, ...]
    diff_truncated: bool
```

Failure modes:
- `git_unavailable`
- `diff_too_large`
- `workspace_not_repo`

### 9. `run_tests`

Purpose:
- Run selected verification commands through `run_command`.

Permission:
- `execute_readonly`

Side effect:
- `executes_process`

Input schema:

```python
@dataclass(frozen=True)
class RunTestsInput:
    test_command: tuple[str, ...]
    cwd: str
    timeout_ms: int
    related_files: tuple[str, ...]
```

Output schema:

```python
@dataclass(frozen=True)
class TestReport:
    exit_code: int
    passed: bool
    summary: str
    failing_tests: tuple[str, ...]
    output_artifact: ArtifactRef
```

Failure modes:
- `test_command_not_allowed`
- `test_timeout`
- `test_failed`
- `test_runner_missing`

Rule:
- A failed test is a valid verification result and should block completion when tests are required.

## Tool Registry

v4 should have a central registry.

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    input_type: type
    output_type: type
    permission_required: str
    side_effect_level: str
    timeout_ms: int
    retry_policy: RetryPolicy
```

Registry responsibilities:
- validate tool existence
- validate input schema
- enforce permission
- enforce timeout
- route execution
- normalize result envelope
- emit telemetry

The planner should never call arbitrary Python functions directly.

## Retry Policy

Retries must be explicit.

Allowed retry cases:
- transient provider unavailable
- read-only command timeout if timeout can be safely increased
- parse failure for typed LLM output

Disallowed retry cases:
- patch conflict without new evidence
- failed tests without a repair plan
- permission denied
- repeated identical retrieval with no changed policy

Retry state must include:
- attempt count
- previous error code
- changed input or policy
- reason retry is expected to help

## Stale Context Policy

Write tools must guard against stale context.

Required checks:
- file content hash before patch
- workspace dirty state
- target file exists
- target span still matches expected content where applicable

If stale:
- block patch
- refresh evidence
- ask planner to revise

## Security Rules

1. No shell-string command construction for workspace mutation.
2. No destructive command execution in normal profiles.
3. No path traversal outside workspace.
4. No silent network access except configured LLM providers.
5. No writing without explicit write permission.
6. No completion success if required verification failed.
7. No hidden fallback from failed write/execute to unverified answer.

## Contract Test Requirements

Every service/tool must have contract tests for:

- valid input
- invalid input
- permission denied
- timeout or failure mode
- telemetry fields present
- artifact refs present when expected
- no side effects beyond declared side-effect level

For config-controlled behavior:
- every config/policy field must have at least one test proving it is consumed.

## Initial Contract Priority

v4 should not implement all tools at once.

Priority order:

1. `CapabilityPolicy`
2. `IndexService`
3. `EvidenceRetrievalService`
4. `EvidenceRankingService`
5. `ContextPackService`
6. `DirectReadService` / `read_file`
7. `search_repo`
8. `VerificationService` with grounding gates
9. `run_command` for allowlisted tests
10. `apply_patch`
11. `inspect_diff`
12. `run_tests`

Reason:
- v4 must first prove clean read-only service boundaries.
- Execution should arrive before writing.
- Writing should arrive only when verification can block completion.

## Initial Contract Decisions

Initial decisions for implementation planning:

1. Use dataclasses for internal contracts; use Pydantic only at CLI/API/config boundaries if needed.
2. Put v4 under `src/homllm_v4/` first to avoid coupling with v3.
3. Use append-only `events.jsonl` as the source of truth, with derived snapshots for debugging.
4. Start with static/project command allowlists; add per-session user approval later.
5. For the first patch-capable milestone, require stale-context, diff-safety, grounding, and at least one task-appropriate verification gate when available.

## Current Conclusion

The v4 tool layer should be contract-first. The first implementation milestone should not add write tools. It should wrap v3 indexing, retrieval, ranking, and context as typed services and prove that the service boundary works without changing behavior.

The next document should define the agent loop and memory model in more detail.
