# HOM-LLM v4 Current System Asset Map and Reuse Strategy

Date: 2026-05-09

## Purpose

This document maps the current HOM-LLM v3 system into a v4 reuse strategy. The goal is not to preserve code because it already exists. The goal is to preserve hard-won capability while avoiding inherited architectural constraints.

v4 should be designed as a multi-pass, tool-capable, evidence-first coding agent. v3 should be treated as a source of proven subsystems, failed assumptions, diagnostics, and evaluation data.

## Strategic Position

The existing system is not junk. It contains a serious code RAG engine with indexing, retrieval, ranking, context assembly, evidence contracts, generation, and evaluation infrastructure. The core failure is that these capabilities were originally assembled around a single-pass read-only answer path, then later stretched toward agentic behavior.

v4 should not be "v3 plus more patches." v4 should be a clean orchestration architecture that can call v3-derived services through typed boundaries.

## Reuse Categories

### Reuse As Service

These components are valuable enough to become v4 services behind stable interfaces.

- Indexing and repository artifact generation
- Retrieval candidate acquisition
- Ranking and reranking
- Context assembly and token budgeting
- Evaluation harness and judge comparison tooling
- Provider abstraction for generation

### Wrap Before Reuse

These components are useful but should not leak their current internal shape into v4.

- Config loading
- Runtime telemetry
- Intelligence and sufficiency signals
- Claim coverage and answer contracts
- Current read-only agentic router/orchestrator prototype

### Mine For Ideas, Rewrite Boundary

These components contain useful lessons but should not define the v4 architecture.

- `runtime/run_query.py`
- Current prompt assembly path
- Current read-only planner prompt
- Current answer-shape enforcement
- Current broad retrieval recovery strategies

### Do Not Carry Forward As Architecture

These are failure patterns, not assets.

- One giant runtime function controlling retrieval, ranking, context, intelligence, generation, and output.
- Agentic loop as an afterthought around a single-pass pipeline.
- Write/execute tools bolted onto read-only state.
- Prompt strings as the primary control system.
- Silent fallback behavior that hides degraded capability.
- Config knobs that exist but do not affect the intended execution path.

## Component Map

### 1. Indexer

Current location:
- `src/homllm/indexer/`
- `runtime/index_repo.py`

Current role:
- Scans repositories.
- Chunks source files.
- Extracts entities, graph relationships, and confidence signals.
- Builds DuckDB, Tantivy/BM25, LanceDB vector, filesystem, and graph artifacts.

Value:
- This is one of the strongest reusable foundations.
- v4 needs repository understanding before agent loops begin.
- The generated artifacts can become the stable evidence substrate for all tools.

Risks:
- Indexing assumptions may be too Python-centric.
- Some graph resolution and type alias behavior appears partial or disabled.
- Artifact schema/versioning must become explicit if v4 depends on it as a service.

v4 boundary:
- `IndexService`
- Inputs: workspace root, include/exclude policy, language profile, rebuild mode.
- Outputs: immutable `RepoIndexManifest`, artifact paths, schema version, warnings.
- Required behavior: no generation, no planning, no write actions.

Reuse decision:
- Reuse the capability.
- Wrap behind a v4 service contract.
- Add schema/version checks before v4 consumes artifacts.

Self-check:
- Can v4 answer "which index produced this evidence" for every tool result?
- Can stale index state block unsafe patching?
- Can the service explain missing files or ignored paths?

### 2. Retrieval

Current location:
- `src/homllm/retrieval/`

Current role:
- Prepares query terms.
- Runs BM25 and vector search.
- Performs hybrid fusion, graph stitching, expansion, precision recovery, and coverage recovery.
- Emits rich telemetry.

Value:
- This is the core HOM-LLM advantage.
- It should become the default evidence acquisition path for v4.
- Recent vector experiments proved retrieval is powerful but can dilute evidence if over-broad.

Risks:
- Retrieval currently mixes multiple responsibilities: query prep, search, fusion, expansion, recovery, and caps.
- Some knobs are indirect or overridden by adaptive behavior.
- Broad vector retrieval can reduce answer quality despite increasing coverage.

v4 boundary:
- `EvidenceRetrievalService`
- Inputs: task intent, query, target symbols/files if known, budget profile, retrieval policy.
- Outputs: `EvidenceSet` with candidates, provenance, scores, source channels, and diagnostics.
- Required behavior: deterministic where possible, no direct file mutation, no final-answer generation.

Reuse decision:
- Reuse heavily, but wrap.
- Split retrieval policy from retrieval execution.
- Make broadening an explicit planner action, not an implicit default.

Self-check:
- Does the caller know why each candidate was included?
- Can v4 request "narrow exact evidence" versus "broad discovery evidence"?
- Can vector evidence be bounded when retrieval disagreement is high?

### 3. Ranking

Current location:
- `src/homllm/ranking/`

Current role:
- Enriches candidates with BM25, dense, name, structural, graph, and reranker features.
- Runs local Qwen reranker when enabled.
- Computes final scores and ranking diagnostics.

Value:
- Strong reusable evidence prioritization layer.
- Reranker and feature diagnostics are essential for token-efficient context assembly.

Risks:
- Ranking currently depends on candidate shape from retrieval.
- Feature weights are powerful but can be hard to reason about across task classes.
- Reranker latency/device failure must remain visible.

v4 boundary:
- `EvidenceRankingService`
- Inputs: `EvidenceSet`, ranking policy, task intent.
- Outputs: `RankedEvidenceSet`, debug traces, confidence/instability metrics.

Reuse decision:
- Reuse as service.
- Preserve diagnostics.
- Require explicit fallback status when reranker is unavailable.

Self-check:
- Can v4 compare two ranked evidence sets across passes?
- Can ranking explain whether sparse, dense, name, graph, or rerank drove a decision?
- Can ranking signal low confidence instead of pretending the top result is reliable?

### 4. Context Assembly

Current location:
- `src/homllm/context/`

Current role:
- Converts ranked candidates into token-bounded context.
- Deduplicates, scores, orders, stitches, and formats blocks.
- Emits context quality and drop traces.

Value:
- This is production-worthy and should be preserved.
- v4 needs context packs for generation, verification, and patch planning.

Risks:
- Current context is optimized for answer generation, not necessarily for patch generation or execution planning.
- Too much context can produce verbose or fragmented answers.
- Too little context can over-trigger "repo gap" style responses.

v4 boundary:
- `ContextPackService`
- Inputs: ranked evidence, output purpose, token budget, citation policy.
- Outputs: `ContextPack`, block manifest, dropped-evidence ledger, token accounting.

Reuse decision:
- Reuse as a service.
- Add purpose-specific context modes:
  - answer
  - planning
  - patching
  - verification
  - failure analysis

Self-check:
- Is the context pack built for the task being performed?
- Can v4 regenerate a smaller or larger pack without rerunning every layer?
- Can the final answer cite only evidence present in the chosen pack?

### 5. Intelligence, Sufficiency, Claim Coverage, and Quality Signals

Current locations:
- `src/homllm/intelligence/`
- `src/homllm/sufficiency/`
- `src/homllm/claim_coverage/`
- `src/homllm/quality/`

Current role:
- Analyze context quality.
- Build answer contracts.
- Detect gaps, obligations, claim coverage, readability, and hallucination risks.
- Some components are diagnostic-only or partially wired.

Value:
- These are strong ingredients for v4 verification and stop rules.
- They can prevent agent loops from continuing blindly.

Risks:
- Some signals are currently prompt-shaping instead of hard control signals.
- Some logic is complex and may be difficult to trust without isolated tests.
- If every signal becomes mandatory, the system may become brittle and verbose.

v4 boundary:
- `SufficiencyService`
- `GroundingVerifier`
- `AnswerContractService`
- `RiskSignalService`

Reuse decision:
- Wrap before reuse.
- Promote only signals that are measurable and explainable.
- Do not let these services directly mutate state; they should return decisions and evidence.

Self-check:
- Is this signal blocking, advisory, or diagnostic?
- What false positive and false negative behavior does it have?
- Does it reduce real failures or only make outputs look more disciplined?

### 6. Generation

Current location:
- `src/homllm/generation/`

Current role:
- Provides provider abstraction.
- Renders templates.
- Parses and validates generation outputs.
- Detects hallucination flags.

Value:
- Provider abstraction is reusable.
- Retry policies and provider-specific behavior are necessary for production.

Risks:
- Prompt assembly is too deeply embedded in runtime flow.
- Prompt strings currently carry too much control responsibility.
- Generation is answer-oriented, not tool-plan-oriented or patch-oriented.

v4 boundary:
- `LLMService`
- `PromptCompiler`
- `OutputParser`

Reuse decision:
- Reuse provider adapters where stable.
- Rewrite prompt assembly boundaries.
- Separate answer generation, planning generation, patch explanation, and verification summarization.

Self-check:
- Is this LLM call producing a plan, an answer, a patch proposal, or a verifier judgment?
- Is the output typed and parseable when it controls tools?
- Can failed parsing be retried safely without tool side effects?

### 7. Current Agent Layer

Current location:
- `src/homllm/agent/`

Current role:
- Defines early typed contracts.
- Routes single-pass versus read-only agentic mode.
- Supports bounded read-only iteration and repetition guard.

Value:
- Useful prototype.
- Shows good instincts: mode enums, task state, loop budget, repetition guard, permission concepts.

Risks:
- It is still shaped around read-only retrieval reruns.
- It does not express write, execution, patch, rollback, or verification as first-class lifecycle stages.
- It is wired through `runtime/run_query.py`, which limits clean composition.

v4 boundary:
- Do not directly extend this as the v4 orchestrator.
- Mine the types and safety ideas.
- Redesign around a full task lifecycle:
  - plan
  - acquire evidence
  - decide tool action
  - execute or patch if permitted
  - verify
  - stop or revise

Reuse decision:
- Use as reference.
- Rewrite orchestrator boundary for v4.

Self-check:
- Can the loop handle both "answer this" and "modify code then verify" without special-case branching everywhere?
- Is every action permission-checked before execution?
- Can the loop stop with a useful blocked state instead of forcing success?

### 8. Runtime Entrypoint

Current location:
- `runtime/run_query.py`

Current role:
- Main end-to-end CLI path.
- Wires config, retrieval, ranking, context, intelligence, generation, telemetry, diagnostics, and presentation.

Value:
- Useful as an execution trace of current behavior.
- Useful for regression comparison.

Risks:
- It is the clearest example of what v4 should not repeat.
- It centralizes too many responsibilities.
- It makes architecture harder to reason about, test, and extend.

v4 boundary:
- Replace with thin CLI/API entrypoints that call an application service.
- Runtime should parse inputs, load config, call the v4 app, and render outputs.
- Runtime should not own orchestration.

Reuse decision:
- Do not use as v4 foundation.
- Preserve as v3 compatibility path until v4 is proven.

Self-check:
- Can a new entrypoint be understood without reading retrieval, ranking, context, and generation internals?
- Can v4 be used from CLI, API, and tests through the same application service?

### 9. Evaluation Harness

Current location:
- `eval/`
- `tests/`
- `artifacts/runs/`

Current role:
- Runs canonical queries.
- Judges outputs.
- Compares runs.
- Stores telemetry and responses.

Value:
- Critical. v4 should be built around evaluation from the start.
- The recent vector regression analysis demonstrates why this matters.

Risks:
- Judge providers can fail or produce partial outputs.
- LLM judging is noisy; comparison must handle missing judgments and repeated runs.
- Current benchmarks are mostly read-only Q&A, not patch/execution tasks.

v4 boundary:
- `EvaluationService`
- `RunLedger`
- `BenchmarkTask`
- `JudgeResult`

Reuse decision:
- Reuse and expand.
- Add patch tasks, execution tasks, token/tool accounting, and retry-safe partial judge handling.

Self-check:
- Can v4 prove a change improved behavior before promotion?
- Can evaluation separate retrieval quality, answer quality, patch correctness, and verification quality?
- Can partial judge failure be detected as incomplete rather than success?

### 10. Configuration

Current location:
- `src/homllm/common/config.py`
- `configs/`

Current role:
- Loads large YAML configs.
- Supplies subsystem settings.

Value:
- Comprehensive and flexible.

Risks:
- Too many knobs can hide architecture flaws.
- Some knobs may not influence behavior as expected.
- Config is not a substitute for typed policy objects.

v4 boundary:
- Keep YAML for presets.
- Convert loaded config into typed policy objects:
  - retrieval policy
  - ranking policy
  - context policy
  - tool permission policy
  - execution policy
  - verification policy

Reuse decision:
- Reuse concepts.
- Tighten typing and validation.
- Every policy field must have a test proving where it is consumed.

Self-check:
- Can we trace every config option to code that uses it?
- Can invalid combinations be rejected early?
- Can product presets be small and understandable?

## v4 Architectural Implications

### Principle 1: RAG Is A Service, Not The Whole Agent

v3 treats retrieval/ranking/context/generation as a pipeline. v4 should treat RAG as a core evidence service that the agent can call repeatedly with different policies.

### Principle 2: Tools Must Be Typed And Permissioned

Every v4 tool should define:

- input schema
- output schema
- permission level
- side effects
- failure modes
- telemetry fields
- retry policy
- verification requirements

### Principle 3: Write Capability Is A Lifecycle, Not A Tool

`write_file` or `patch_file` is not enough. Write-capable behavior requires:

- precondition evidence
- patch plan
- stale-context check
- patch application
- diff manifest
- verification command selection
- verification execution
- failure repair or rollback decision
- final explanation

### Principle 4: Multi-Pass Must Be Bounded

The loop must have explicit budgets:

- max LLM calls
- max retrieval passes
- max tool calls
- max patch attempts
- max verification attempts
- max tokens
- max wall-clock time
- repeated-state stop rules

### Principle 5: Evaluation Must Drive Promotion

No v4 capability should be considered real until it passes targeted evaluation:

- read-only explanation tasks
- debugging tasks
- small patch tasks
- command/test verification tasks
- regression tasks from v3 canaries

## Recommended v4 Service Boundary Draft

```text
User Task
  -> TaskIntakeService
  -> PlannerService
  -> EvidenceRetrievalService
  -> EvidenceRankingService
  -> ContextPackService
  -> ToolExecutor
  -> PatchService
  -> VerificationService
  -> ResponseService
  -> Evaluation/Telemetry Ledger
```

## Initial Keep / Change / Reject Table

| Area | Keep | Change | Reject |
| --- | --- | --- | --- |
| Indexing | artifact generation, graph, embeddings | schema/version contracts | implicit stale-index behavior |
| Retrieval | BM25, vector, graph, recovery | explicit evidence policies | unbounded broadening |
| Ranking | reranker, feature traces | typed confidence outputs | hidden degraded reranker state |
| Context | token budgeting, block provenance | purpose-specific context packs | one context format for all tasks |
| Intelligence | sufficiency/coverage signals | service outputs and gates | prompt-only control |
| Generation | provider adapters | prompt compiler separation | monolithic prompt assembly |
| Agent | mode/task state ideas | full lifecycle orchestrator | read-only loop as final architecture |
| Runtime | CLI compatibility | thin entrypoints | god-function orchestration |
| Eval | run/judge/compare infrastructure | patch/tool benchmarks | partial judge success ambiguity |

## Current Conclusion

v4 should be built beside v3, not inside the current runtime path. The current RAG engine should be converted into services and tools with typed contracts. The orchestration layer should be redesigned from first principles around multi-pass evidence acquisition, safe tool use, write capability, and verification.

The next document should define the v4 first-principles architecture before any new code is created.

