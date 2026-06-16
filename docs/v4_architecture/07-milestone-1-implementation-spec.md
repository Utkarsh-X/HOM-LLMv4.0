# HOM-LLM v4 Milestone 1 Implementation Spec

Date: 2026-05-09

## Purpose

This document narrows Milestone 1 into an implementation-ready specification.

Milestone 1 builds the v4 service shell only. It does not build the agent loop, command execution, patching, sandbox runtime, approval UX, product UI, or write tools.

The goal is to prove that v4 can call v3 RAG capabilities through clean contracts, record an append-only run ledger, write inspectable artifacts, and produce a read-only context pack without changing v3 behavior.

## Scope

### Included

- `src/homllm_v4/` package boundary.
- Dataclass-based internal contracts.
- JSON serialization helpers.
- Central `CapabilityPolicy`.
- Append-only `events.jsonl` run ledger.
- Artifact manager under `.homllm/runs/<run_id>/`.
- Service registry.
- v3 adapter interfaces.
- Index validation/manifest shell.
- Retrieval adapter around `homllm.retrieval.pipeline.RetrievalPipeline`.
- Ranking adapter around `homllm.ranking.pipeline.RankingPipeline`.
- Context adapter around `homllm.context.pipeline.ContextPipeline`.
- Direct read service.
- Minimal read-only runtime path: retrieve -> rank -> context.
- Contract tests.

### Excluded

- LLM generation.
- Multi-pass planning.
- Sufficiency loop.
- Claim support map.
- Command execution.
- Patch application.
- Verification command gates.
- Sandbox backend.
- Approval flow.
- Product UI.
- External benchmarks.

## Target Package Tree

Create this exact v4 package tree:

```text
src/homllm_v4/
  __init__.py
  app/
    __init__.py
    readonly_context_app.py
  artifacts/
    __init__.py
    manager.py
  contracts/
    __init__.py
    artifacts.py
    capability.py
    context.py
    errors.py
    evidence.py
    index.py
    policy.py
    ranking.py
    task.py
    telemetry.py
  ledger/
    __init__.py
    events.py
    writer.py
  registry/
    __init__.py
    service_registry.py
  services/
    __init__.py
    context_service.py
    direct_read_service.py
    index_service.py
    ranking_service.py
    retrieval_service.py
  adapters/
    __init__.py
    v3_context_adapter.py
    v3_index_adapter.py
    v3_ranking_adapter.py
    v3_retrieval_adapter.py
  serialization/
    __init__.py
    json.py
```

Create this exact test tree:

```text
tests/unit/v4/
  test_artifact_manager.py
  test_capability_result.py
  test_direct_read_service.py
  test_event_writer.py
  test_index_service_contract.py
  test_readonly_context_app_contract.py
  test_service_registry.py
  test_v3_adapter_boundaries.py
```

No existing v3 files should be modified in Milestone 1 unless an adapter boundary proves impossible without a small compatibility shim. If that happens, stop and review before changing v3.

## Module Responsibilities

### `contracts/`

Owns dataclasses only.

Rules:
- no imports from `homllm`
- no filesystem access
- no service execution
- no runtime orchestration
- no model/provider calls
- contract invariants must be enforced in the dataclass when invalid states would corrupt runtime behavior

### `serialization/`

Owns conversion between dataclasses and JSON-compatible dictionaries.

Rules:
- pass through `None`, `bool`, `int`, `float`, and `str`
- support nested dataclasses
- support tuples as JSON arrays
- preserve stable field names
- include schema version where defined
- do not silently drop unknown required fields when deserializing

### `artifacts/`

Owns run directory creation and artifact file writes.

Rules:
- writes only under configured artifact root
- default artifact root is `.homllm/runs`
- each run has its own directory
- creates subdirectories exactly as specified
- returns `ArtifactRef` for each written artifact

### `ledger/`

Owns append-only event writing.

Rules:
- `events.jsonl` is the source of truth
- one JSON object per line
- event writer appends only
- event ids are unique per run
- snapshots are not required in Milestone 1

### `registry/`

Owns service registration and lookup.

Rules:
- registry maps stable service names to service objects
- duplicate names are rejected
- missing service lookup returns structured error or raises a v4-owned exception
- registry does not instantiate v3 dependencies by itself

### `services/`

Owns v4 service interfaces.

Rules:
- services accept v4 request dataclasses
- services return `CapabilityResult`
- services write events and artifacts through injected dependencies
- services may call adapters
- services do not import v3 pipelines directly except through adapter classes

### `adapters/`

Owns v3 integration.

Rules:
- adapters may import `homllm.*`
- adapters translate between v4 contracts and v3 objects
- all translation from v4 policies/contracts into v3 config objects is owned exclusively by `adapters/`
- services may not construct v3 config objects directly
- adapters must not expose raw v3 objects through v4 service outputs
- adapters must preserve degraded/fallback diagnostics where available

### `app/`

Owns the minimal Milestone 1 execution path.

Rules:
- app wires policy, artifact manager, ledger, registry, and services
- app runs retrieve -> rank -> context
- app returns a v4 result object or dictionary suitable for tests
- app does not call LLM generation
- app does not loop

## Core Contract Schemas

All internal schemas are frozen dataclasses.

Use Python syntax compatible with the repository runtime. Avoid Python 3.12-only generic class syntax such as `class CapabilityResult[T]`. Use `Generic[T]` if generics are implemented.

### `CapabilityError`

Location:
- `src/homllm_v4/contracts/errors.py`

Fields:

```python
@dataclass(frozen=True)
class CapabilityError:
    code: str
    message: str
    recoverable: bool
    retryable: bool
    details: dict[str, object]
```

Initial error codes:
- `index_missing`
- `index_stale`
- `schema_mismatch`
- `permission_denied`
- `path_denied`
- `file_not_found`
- `file_too_large`
- `binary_file_denied`
- `empty_evidence_set`
- `adapter_failed`
- `serialization_failed`
- `artifact_write_failed`
- `service_not_registered`

### `ArtifactRef`

Location:
- `src/homllm_v4/contracts/artifacts.py`

Fields:

```python
@dataclass(frozen=True)
class ArtifactRef:
    artifact_type: str
    path: str
    description: str
    content_hash: str | None
```

### `CapabilityTelemetry`

Location:
- `src/homllm_v4/contracts/telemetry.py`

Fields:

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

### `CapabilityResult`

Location:
- `src/homllm_v4/contracts/capability.py`

Fields:

```python
T = TypeVar("T")

@dataclass(frozen=True)
class CapabilityResult(Generic[T]):
    capability_name: str
    ok: bool
    output: T | None
    error: CapabilityError | None
    telemetry: CapabilityTelemetry
    artifacts: tuple[ArtifactRef, ...]
```

Rules:
- `ok=True` requires `output is not None` and `error is None`.
- `ok=False` requires `error is not None`.
- degraded success is represented by `ok=True` and `telemetry.degraded=True`.
- these invariants must be enforced in `CapabilityResult.__post_init__`, not only in tests
- `ok=False` may have `output=None`; partial diagnostic details belong in `CapabilityError.details` and artifacts

Required invariant implementation:

```python
def __post_init__(self) -> None:
    if self.ok:
        if self.output is None:
            raise ValueError("successful CapabilityResult requires output")
        if self.error is not None:
            raise ValueError("successful CapabilityResult cannot include error")
    elif self.error is None:
        raise ValueError("failed CapabilityResult requires error")
```

### `CapabilityPolicy`

Location:
- `src/homllm_v4/contracts/policy.py`

Fields:

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

Milestone 1 default:

```python
CapabilityPolicy(
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
    blocked_tools=(
        "command.run",
        "patch.apply",
        "tests.run",
    ),
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
```

`escalation_rules` is reserved for future milestones. Milestone 1 stores it but does not interpret it.

### `RunEvent`

Location:
- `src/homllm_v4/ledger/events.py`

Fields:

```python
@dataclass(frozen=True)
class RunEvent:
    event_id: str
    run_id: str
    task_id: str
    phase: str
    event_type: str
    timestamp: str
    summary: dict[str, object]
    artifact_refs: tuple[ArtifactRef, ...]
```

Required event types for Milestone 1:
- `run_started`
- `policy_created`
- `artifact_written`
- `index_validated`
- `retrieval_completed`
- `ranking_completed`
- `context_completed`
- `service_failed`
- `run_completed`

Event type strings are centralized in `ledger/events.py` for Milestone 1. A stricter enum can be introduced later if event taxonomy starts expanding.

## Service Contracts For Milestone 1

## Adapter Translation Responsibilities

Adapters are compatibility translation layers, not thin pass-through wrappers.

The service layer owns v4 contracts and policy enforcement. The adapter layer owns all v3 object construction and v3 compatibility decisions.

Global rules:
- all v4-to-v3 config mapping lives in `src/homllm_v4/adapters/`
- `services/` may not import or instantiate v3 config classes
- `services/` may not import `homllm.retrieval`, `homllm.ranking`, `homllm.context`, or `homllm.indexer` directly
- adapters return only v4 dataclasses or primitive diagnostics
- adapters must preserve degraded flag, degradation reason, and partial channel success
- degraded success is always `ok=True` plus `CapabilityTelemetry.degraded=True`

### Retrieval Adapter Translation

Inputs owned by v4:
- `EvidenceRetrievalRequest`
- `RetrievalPolicy`
- `CapabilityPolicy`
- index artifact paths from `RepoIndexManifest`

v3 objects the adapter may construct:
- `homllm.retrieval.interfaces.RetrievalConfig`
- `homllm.common.types.Intent`
- `homllm.retrieval.pipeline.RetrievalPipeline`

Mapping owned by adapter:
- `RetrievalPolicy.bm25_top_k` and `vector_top_k` to v3 retrieval config fields
- `RetrievalPolicy.graph_enabled` and `graph_max_depth` to graph stitch settings
- `RetrievalPolicy.precision_recovery_enabled` to precision recovery settings
- `RetrievalPolicy.coverage_recovery_enabled` to coverage recovery settings
- `RetrievalPolicy.vector_mode` to vector enablement and vector candidate caps
- `task_class` to v3 `Intent` where possible

### Ranking Adapter Translation

Inputs owned by v4:
- `EvidenceRankingRequest`
- `RankingPolicy`
- v4 `EvidenceSet`

v3 objects the adapter may construct:
- `homllm.ranking.interfaces.RankConfig`
- `homllm.ranking.interfaces.RankingInput`
- `homllm.ranking.pipeline.RankingPipeline`

Mapping owned by adapter:
- v4 `EvidenceCandidate` to v3 candidate-compatible objects
- `RankingPolicy.reranker_enabled`, `reranker_model`, and `reranker_top_m` to `RankConfig`
- ranking weights to `RankConfig`
- v3 debug traces back to v4 ranking diagnostics

### Context Adapter Translation

Inputs owned by v4:
- `ContextPackRequest`
- `ContextPolicy`
- v4 `RankedEvidenceSet`

v3 objects the adapter may construct:
- `homllm.context.interfaces.ContextConfig`
- v3 `RankingOutput`-compatible object
- `homllm.context.pipeline.ContextPipeline`

Mapping owned by adapter:
- `ContextPolicy.max_tokens` to `ContextConfig.max_tokens`
- `ContextPolicy.purpose` to adapter-selected v3 context config profile
- v4 ranked evidence to v3 ranked candidate shape
- v3 `ContextArtifact` to v4 `ContextPack`

### Index Adapter Translation

Inputs owned by v4:
- `IndexRequest`
- workspace root
- configured artifact paths

v3 objects the adapter may construct:
- storage adapters such as `DuckDBAdapter`, `TantivyAdapter`, and `LanceDBAdapter`

Mapping owned by adapter:
- v3 artifact presence to `RepoIndexManifest`
- v3 schema/version metadata to `RepoIndexManifest.schema_version`
- artifact modified times and workspace state to `IndexFreshness`

### Direct Read Has No v3 Adapter

`DirectReadService` is implemented directly in v4 because it validates current filesystem state. It exists for precision validation and freshness-sensitive operations, not as the primary repository understanding mechanism.

### `IndexService`

Location:
- `src/homllm_v4/services/index_service.py`

Adapter:
- `src/homllm_v4/adapters/v3_index_adapter.py`

v3 dependencies:
- `homllm.indexer.storage.duckdb_adapter.DuckDBAdapter`
- index artifact paths produced by current v3 indexing flow

Request:
- `IndexRequest` from `contracts/index.py`

Output:
- `RepoIndexManifest`
- `IndexFreshness`

Milestone 1 behavior:
- validate that configured artifact paths exist
- validate schema/version if available
- report vector/BM25/DuckDB artifact presence
- report `possibly_stale` when workspace files are newer than index artifacts
- do not rebuild the index unless explicitly called with `mode="rebuild"` in a later milestone

### `EvidenceRetrievalService`

Location:
- `src/homllm_v4/services/retrieval_service.py`

Adapter:
- `src/homllm_v4/adapters/v3_retrieval_adapter.py`

v3 dependency:
- `homllm.retrieval.pipeline.RetrievalPipeline`

Request:
- `EvidenceRetrievalRequest`

Output:
- `EvidenceSet`

Milestone 1 behavior:
- call `RetrievalPipeline.retrieve(query, intent, top_k)`
- map v3 candidates into v4 `EvidenceCandidate`
- preserve `bm25_count`, `vector_count`, graph/recovery counts where available
- mark degraded if vector/BM25 channel fails but the other succeeds
- write raw candidate artifact under `evidence/`

### `EvidenceRankingService`

Location:
- `src/homllm_v4/services/ranking_service.py`

Adapter:
- `src/homllm_v4/adapters/v3_ranking_adapter.py`

v3 dependency:
- `homllm.ranking.pipeline.RankingPipeline`

Request:
- `EvidenceRankingRequest`

Output:
- `RankedEvidenceSet`

Milestone 1 behavior:
- translate v4 `EvidenceSet` to v3 `RankingInput`
- call `RankingPipeline.rank(...)`
- map ranked candidates and debug traces into v4 output
- preserve reranker diagnostics and degraded status
- write ranking artifact under `evidence/` or `context/` as configured

### `ContextPackService`

Location:
- `src/homllm_v4/services/context_service.py`

Adapter:
- `src/homllm_v4/adapters/v3_context_adapter.py`

v3 dependency:
- `homllm.context.pipeline.ContextPipeline`

Request:
- `ContextPackRequest`

Output:
- `ContextPack`

Milestone 1 behavior:
- translate v4 `RankedEvidenceSet` to v3 `RankingOutput` shape
- call `ContextPipeline.assemble(...)`
- map blocks, token usage, dropped evidence, and provenance into v4 output
- write context artifact under `context/`

### `DirectReadService`

Location:
- `src/homllm_v4/services/direct_read_service.py`

Adapter:
- none

Request:
- `DirectReadRequest`

Output:
- `DirectReadResult`

Milestone 1 behavior:
- path must resolve inside workspace root
- reads text files only
- returns content hash when `require_hash=True`
- supports optional line slicing
- enforces `max_bytes`
- writes direct-read artifact only when caller requests it

## Service Registry

Location:
- `src/homllm_v4/registry/service_registry.py`

Required API:

```python
class ServiceRegistry:
    def register(self, name: str, service: object) -> None: ...
    def get(self, name: str, expected_type: type[T]) -> T: ...
    def names(self) -> tuple[str, ...]: ...
```

Milestone 1 service names:
- `index.validate`
- `evidence.retrieve`
- `evidence.rank`
- `context.build`
- `file.read`

Registry rules:
- duplicate registration raises a v4-owned exception
- missing lookup raises a v4-owned exception
- lookup with the wrong `expected_type` raises a v4-owned exception
- registry does not import v3
- registry does not create services automatically
- do not introduce a dependency injection framework, plugin architecture, reflection system, or broad service locator

## Artifact Manager

Location:
- `src/homllm_v4/artifacts/manager.py`

Default run directory:

```text
.homllm/runs/<run_id>/
```

Required layout:

```text
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

Required API:

```python
class ArtifactManager:
    def create_run(self, run_id: str, metadata: dict[str, object]) -> None: ...
    def write_json(self, relative_path: str, payload: object, artifact_type: str, description: str) -> ArtifactRef: ...
    def write_text(self, relative_path: str, text: str, artifact_type: str, description: str) -> ArtifactRef: ...
    def resolve_artifact_path(self, relative_path: str) -> Path: ...
```

Path rules:
- artifact paths must stay inside the run directory
- path traversal is denied
- writes are atomic where practical
- returned `ArtifactRef.path` is relative to workspace root or absolute consistently; choose one in implementation and test it
- content hashes use SHA256 over UTF-8 encoded normalized bytes for text/JSON artifacts

Initial decision:
- use workspace-relative paths for artifact refs when possible
- use absolute paths only when workspace-relative conversion is impossible

## Event Writer

Location:
- `src/homllm_v4/ledger/writer.py`

Required API:

```python
class EventWriter:
    def append(self, event: RunEvent) -> None: ...
```

Rules:
- append only
- JSONL one event per line
- each `append` writes exactly one JSON line
- each `append` flushes immediately
- append order is preserved
- no event mutation
- event serialization uses `serialization/json.py`
- failed event write raises a v4-owned exception
- fsync, checksum validation, and corruption recovery are deferred beyond Milestone 1

## Minimal Runtime Path

Location:
- `src/homllm_v4/app/readonly_context_app.py`

Required API:

```python
def build_readonly_context(
    *,
    task_id: str,
    run_id: str,
    workspace_root: str,
    query: str,
    service_registry: ServiceRegistry,
    artifact_manager: ArtifactManager,
    event_writer: EventWriter,
    policy: CapabilityPolicy,
) -> CapabilityResult[ContextPack]:
    ...
```

Execution path:

```text
run_started
  -> policy_created
  -> index.validate
  -> evidence.retrieve
  -> evidence.rank
  -> context.build
  -> run_completed
```

Failure behavior:
- if `index.validate` fails, stop and return failed `CapabilityResult`
- if retrieval returns no candidates, stop with `empty_evidence_set`
- if ranking fails, stop with ranking error
- if context build fails, stop with context error
- every failure writes `service_failed`

Runtime path constraints:
- no LLM calls
- no command execution
- no writes outside artifact directory
- no patching
- no retries except adapter-local safe fallback already present in v3

## v3 Wrapper Boundaries

Milestone 1 adapters may import from v3; v4 services outside `adapters/` should not import v3 directly.

Allowed v3 imports by adapter:

```text
v3_retrieval_adapter.py
  homllm.retrieval.pipeline.RetrievalPipeline
  homllm.retrieval.interfaces.RetrievalConfig
  homllm.common.types.Intent

v3_ranking_adapter.py
  homllm.ranking.pipeline.RankingPipeline
  homllm.ranking.interfaces.RankConfig
  homllm.ranking.interfaces.RankingInput

v3_context_adapter.py
  homllm.context.pipeline.ContextPipeline
  homllm.context.interfaces.ContextConfig

v3_index_adapter.py
  homllm.indexer.storage.duckdb_adapter.DuckDBAdapter
  homllm.indexer.storage.tantivy_adapter.TantivyAdapter
  homllm.indexer.storage.lancedb_adapter.LanceDBAdapter
```

Adapter outputs must be v4 dataclasses only.

## Contract Serialization

Location:
- `src/homllm_v4/serialization/json.py`

Required functions:

```python
def to_jsonable(value: object) -> object: ...
def write_json_file(path: Path, value: object) -> None: ...
def read_json_file(path: Path) -> dict[str, object]: ...
```

Rules:
- `None`, `bool`, `int`, `float`, and `str` pass through unchanged
- dataclasses become dictionaries
- tuples become lists
- paths become strings
- unsupported objects raise `serialization_failed`
- output must be deterministic enough for tests

## Tests Required Before Implementation Is Considered Complete

### `test_capability_result.py`

Proves:
- success result requires output and no error
- failure result requires error
- degraded success is representable
- serialization preserves fields

### `test_artifact_manager.py`

Proves:
- run directory layout is created
- JSON artifact writes return `ArtifactRef`
- path traversal is denied
- artifact hash is stable for same content

### `test_event_writer.py`

Proves:
- events append to `events.jsonl`
- each line is valid JSON
- two events preserve order
- serialized `ArtifactRef` is present

### `test_service_registry.py`

Proves:
- service registration works
- duplicate registration fails
- missing lookup fails
- lookup with wrong expected type fails
- registry names are stable

### `test_direct_read_service.py`

Proves:
- reads a workspace file
- returns content hash
- line slicing works
- path outside workspace is denied
- large file limit is enforced

### `test_index_service_contract.py`

Proves:
- missing index artifacts return `index_missing`
- present artifact paths produce `RepoIndexManifest`
- freshness can be `fresh` or `possibly_stale`
- no index rebuild occurs in validate mode

### `test_v3_adapter_boundaries.py`

Proves:
- AST scan proves v4 `services/`, `contracts/`, `registry/`, `ledger/`, `artifacts/`, `serialization/`, and `app/` do not import forbidden v3 modules directly
- forbidden imports include `homllm.retrieval`, `homllm.ranking`, `homllm.context`, and `homllm.indexer`
- v3 imports are limited to `adapters/`
- adapter outputs are v4 dataclasses

### `test_readonly_context_app_contract.py`

Proves:
- app executes services in order using fake services
- app writes required events
- app stops on index failure
- app stops on empty evidence
- app returns `CapabilityResult[ContextPack]`

## Milestone 1 Exit Criteria

Milestone 1 is complete when:

- `src/homllm_v4/` exists with the specified package tree.
- Internal contracts are dataclasses and serialize to JSON.
- `CapabilityPolicy` exists and is used by the minimal app.
- Artifact manager writes the required run directory structure.
- Event writer appends valid `events.jsonl`.
- Service registry registers and resolves the five Milestone 1 services.
- v3 adapters isolate all direct v3 imports.
- Minimal read-only context app runs through fake services in unit tests.
- At least one integration/smoke path can run through real v3 retrieval/ranking/context if existing test artifacts are available.
- v3 runtime behavior remains unchanged.
- No write, execute, patch, approval, sandbox backend, or generation capability is introduced.

## Non-Negotiable Guardrails

- Do not modify v3 orchestration to make Milestone 1 easier.
- Do not add an agent loop.
- Do not add command execution.
- Do not add patch tools.
- Do not add LLM generation.
- Do not add a product UI.
- Do not create extra abstraction layers beyond the package tree above.
- Do not let services outside `adapters/` import v3 internals directly.

## Handoff To Implementation Plan

The next document should be a task-by-task implementation plan for this spec.

That plan should use TDD and should be split roughly as:

1. Contracts and serialization.
2. Artifact manager and event writer.
3. Service registry.
4. Direct read service.
5. Index service shell.
6. v3 adapter boundary tests.
7. Retrieval/ranking/context adapter shells.
8. Minimal read-only context app with fake services.
9. Optional smoke test against real v3 artifacts.

No implementation should begin until this spec is reviewed and accepted.
