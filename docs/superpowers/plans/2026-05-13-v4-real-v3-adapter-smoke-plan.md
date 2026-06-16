# v4 Real v3 Adapter Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the v4 service shell to real v3 retrieval, ranking, and context adapter boundaries without allowing v3 imports to leak outside `src/homllm_v4/adapters/`.

**Architecture:** v4 services remain contract-owned and return `CapabilityResult`. v3 adapters own all translation between v4 contracts and v3 pipeline objects/configs. Unit tests use fake v3-shaped pipelines for deterministic translation checks; an optional real smoke test can be enabled only when local index artifacts and runtime dependencies are available.

**Tech Stack:** Python dataclasses, pytest, v3 `RetrievalPipeline`/`RankingPipeline`/`ContextPipeline` interfaces, existing v4 contracts.

---

## Implementation Boundary

Do not implement:

- planner loop
- generation
- patch/write tools
- command execution
- sandbox runtime
- real benchmark judging

Do not instantiate heavyweight v3 GPU models in default unit tests.

## Files

Modify:

- `src/homllm_v4/adapters/v3_retrieval_adapter.py`
- `src/homllm_v4/adapters/v3_ranking_adapter.py`
- `src/homllm_v4/adapters/v3_context_adapter.py`
- `src/homllm_v4/services/retrieval_service.py`
- `src/homllm_v4/services/ranking_service.py`
- `src/homllm_v4/services/context_service.py`
- `tests/unit/v4/test_v3_adapter_boundaries.py`

Create:

- `tests/unit/v4/test_v3_adapter_translation.py`

## Task 1: Adapter Translation Tests

- [ ] **Step 1: Add fake v3 pipeline objects in `tests/unit/v4/test_v3_adapter_translation.py`**

Create fakes with the same public methods used by adapters:

- retrieval fake exposes `retrieve(query, intent, top_k)`
- ranking fake exposes `rank(input_data)`
- context fake exposes `assemble(ranking_output, query, query_id=None, unresolved_claim_hints=None)`

- [ ] **Step 2: Assert retrieval translation**

Test that `V3RetrievalAdapter.retrieve()`:

- passes `request.query`
- maps policy `intent` and `top_k`
- maps v3 candidates into `EvidenceCandidate`
- preserves candidate content in `metadata["content"]`
- maps v3 metadata counts into `RetrievalDiagnostics`

- [ ] **Step 3: Assert ranking translation**

Test that `V3RankingAdapter.rank()`:

- reconstructs v3 candidates from v4 evidence candidates
- passes query from `EvidenceSet.query`
- maps ranked order, final scores, rerank flag, and diagnostics

- [ ] **Step 4: Assert context translation**

Test that `V3ContextAdapter.build()`:

- reconstructs a v3 ranking output from `RankedEvidenceSet`
- passes query from policy `query`
- maps context text, blocks, token count, and provenance diagnostics into `ContextPack`

- [ ] **Step 5: Run red test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_v3_adapter_translation.py -q
```

Expected:

- Fails because adapter methods are not implemented yet.

## Task 2: Adapter Implementations

- [ ] **Step 1: Implement `V3RetrievalAdapter`**

Constructor accepts a v3-shaped pipeline object. `retrieve(request)` returns v4 `EvidenceSet`. Real v3 imports are allowed only in this adapter file.

- [ ] **Step 2: Implement `V3RankingAdapter`**

Constructor accepts a v3-shaped pipeline object. `rank(request)` returns v4 `RankedEvidenceSet`. Candidate content must round-trip through `EvidenceCandidate.metadata["content"]`.

- [ ] **Step 3: Implement `V3ContextAdapter`**

Constructor accepts a v3-shaped pipeline object. `build(request)` returns v4 `ContextPack`. It must not call generation.

- [ ] **Step 4: Run adapter translation tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_v3_adapter_translation.py -q
```

Expected:

- All adapter translation tests pass.

## Task 3: Service Integration

- [ ] **Step 1: Update service shells**

Update retrieval, ranking, and context services so they accept optional adapters and return `CapabilityResult` with structured telemetry.

- [ ] **Step 2: Add service-level translation test if needed**

If adapter tests do not cover `CapabilityResult` behavior, add assertions to `tests/unit/v4/test_v3_adapter_translation.py`.

- [ ] **Step 3: Run v4 tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4 -q
```

Expected:

- All v4 tests pass.

## Task 4: Boundary And Optional Real Smoke

- [ ] **Step 1: Keep boundary test green**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/v4/test_v3_adapter_boundaries.py -q
```

Expected:

- Boundary test passes.

- [ ] **Step 2: Add optional real smoke only if cheap**

If local artifacts are usable without downloading models or causing long GPU runs, add an opt-in test gated by `HOMLLM_V4_RUN_REAL_V3_SMOKE=1`.

Default CI/local unit runs must not execute heavyweight v3 pipelines.

## Completion Criteria

- `tests/unit/v4/test_v3_adapter_translation.py` passes.
- `tests/unit/v4` passes.
- Boundary test proves v3 imports remain adapter-only.
- No claim is made that real v3 artifact smoke passed unless the opt-in smoke test is actually run.
